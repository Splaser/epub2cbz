import argparse
import io
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import cv2
import numpy as np
from PIL import Image


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
PREVIEW_LONG_EDGE = 1000
SATURATION_THRESHOLD = 8
DARK_THRESHOLD = 175
PROJECTION_THRESHOLD = 0.10
SPARSE_PAGE_THRESHOLD = 0.37
MIN_EXPECTED_SPAN_RATIO = 0.82


@dataclass(frozen=True)
class PageDetection:
    name: str
    width: int
    height: int
    box: tuple[int, int, int, int]
    foreground_ratio: float


def _largest_projection_run(values: np.ndarray) -> tuple[int, int]:
    """Return the longest dense run, ignoring isolated scanner dust and shadows."""
    smooth_width = min(7, len(values))
    smoothed = np.convolve(
        values,
        np.ones(smooth_width, dtype=np.float32) / smooth_width,
        mode="same",
    )
    active = (smoothed > PROJECTION_THRESHOLD).astype(np.uint8)
    close_width = max(3, round(len(active) * 0.02))
    active = cv2.morphologyEx(
        active[None, :],
        cv2.MORPH_CLOSE,
        np.ones((1, close_width), dtype=np.uint8),
    )[0]

    changes = np.diff(np.r_[False, active.astype(bool), False].astype(np.int8))
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    if not len(starts):
        return 0, len(values)
    best = int(np.argmax(ends - starts))
    return int(starts[best]), int(ends[best])


def detect_page(name: str, data: bytes) -> PageDetection:
    encoded = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cannot decode image: {name}")

    height, width = image.shape[:2]
    scale = min(1.0, PREVIEW_LONG_EDGE / max(width, height))
    if scale < 1.0:
        preview = cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA,
        )
    else:
        preview = image

    blurred = cv2.GaussianBlur(preview, (5, 5), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
    foreground = (
        (hsv[:, :, 1] > SATURATION_THRESHOLD) | (gray < DARK_THRESHOLD)
    ).astype(np.uint8)

    left, right = _largest_projection_run(foreground.mean(axis=0))
    top, bottom = _largest_projection_run(foreground.mean(axis=1))
    inv_scale = 1.0 / scale
    box = (
        max(0, int(np.floor(left * inv_scale))),
        max(0, int(np.floor(top * inv_scale))),
        min(width, int(np.ceil(right * inv_scale))),
        min(height, int(np.ceil(bottom * inv_scale))),
    )
    return PageDetection(
        name=name,
        width=width,
        height=height,
        box=box,
        foreground_ratio=float(foreground.mean()),
    )


def _consensus_box(pages: list[PageDetection]) -> tuple[int, int, int, int]:
    return tuple(round(median(page.box[index] for page in pages)) for index in range(4))


def normalize_boxes(
    detections: list[PageDetection], padding: int = 12
) -> dict[str, tuple[int, int, int, int]]:
    """Use odd/even page consensus when a nearly white page has weak boundaries."""
    parity_groups = {
        parity: [page for index, page in enumerate(detections) if index % 2 == parity]
        for parity in (0, 1)
    }
    consensus = {
        parity: _consensus_box(group)
        for parity, group in parity_groups.items()
        if group
    }

    normalized: dict[str, tuple[int, int, int, int]] = {}
    for index, page in enumerate(detections):
        left, top, right, bottom = page.box
        expected = consensus.get(index % 2, page.box)
        expected_width = max(1, expected[2] - expected[0])
        expected_height = max(1, expected[3] - expected[1])
        detected_width = right - left
        detected_height = bottom - top
        is_sparse = page.foreground_ratio < SPARSE_PAGE_THRESHOLD

        if is_sparse and detected_width < expected_width * MIN_EXPECTED_SPAN_RATIO:
            left, right = expected[0], expected[2]
        if is_sparse and detected_height < expected_height * MIN_EXPECTED_SPAN_RATIO:
            top, bottom = expected[1], expected[3]

        normalized[page.name] = (
            max(0, left - padding),
            max(0, top - padding),
            min(page.width, right + padding),
            min(page.height, bottom + padding),
        )
    return normalized


def _encode_cropped_image(data: bytes, box: tuple[int, int, int, int]) -> bytes:
    with Image.open(io.BytesIO(data)) as image:
        if box == (0, 0, image.width, image.height):
            return data

        cropped = image.crop(box)
        # Pillow clears ``format`` on derived images; JPEG's ``keep`` options
        # need it to know that the source quantization/subsampling are reusable.
        cropped.format = image.format
        output = io.BytesIO()
        save_kwargs = {}
        if image.info.get("icc_profile"):
            save_kwargs["icc_profile"] = image.info["icc_profile"]
        if image.info.get("exif"):
            save_kwargs["exif"] = image.info["exif"]

        image_format = image.format or "JPEG"
        if image_format == "JPEG":
            save_kwargs.update(quality="keep", subsampling="keep", optimize=True)
        elif image_format == "PNG":
            save_kwargs.update(optimize=True)
        elif image_format == "WEBP":
            save_kwargs.update(quality=95, method=4)
        cropped.save(output, format=image_format, **save_kwargs)
        return output.getvalue()


def crop_cbz(
    source: Path,
    output: Path,
    *,
    padding: int = 12,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[int, int]:
    source = source.resolve()
    output = output.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.casefold() != ".cbz":
        raise ValueError(f"not a CBZ file: {source}")
    if not dry_run and output.exists() and not force:
        raise FileExistsError(f"output already exists: {output}")

    temporary: Path | None = None
    try:
        with zipfile.ZipFile(source, "r") as archive:
            infos = archive.infolist()
            image_infos = [
                info
                for info in infos
                if not info.is_dir()
                and Path(info.filename).suffix.casefold() in IMAGE_EXTS
            ]
            if not image_infos:
                raise ValueError(f"no images found in: {source}")

            detections = [
                detect_page(info.filename, archive.read(info)) for info in image_infos
            ]
            boxes = normalize_boxes(detections, padding=padding)
            changed = sum(
                boxes[page.name] != (0, 0, page.width, page.height)
                for page in detections
            )

            for page in detections:
                left, top, right, bottom = boxes[page.name]
                print(
                    f"  - {page.name}: {page.width}x{page.height} -> "
                    f"{right - left}x{bottom - top} "
                    f"[{left},{top},{right},{bottom}]"
                )

            if dry_run:
                return changed, len(detections)

            output.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{output.stem}.", suffix=".tmp", dir=output.parent
            )
            os.close(fd)
            temporary = Path(temporary_name)
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as destination:
                for info in infos:
                    data = archive.read(info)
                    if info.filename in boxes:
                        data = _encode_cropped_image(data, boxes[info.filename])
                    destination.writestr(info, data)

        # On Windows the input archive must be closed before replacing it.
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

    return changed, len(detections)


def _default_output(source: Path) -> Path:
    return source.with_name(f"{source.stem}.cropped{source.suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crop scanner whitespace from every image in a CBZ archive."
    )
    parser.add_argument("cbz", type=Path, help="input CBZ file")
    parser.add_argument("-o", "--output", type=Path, help="output CBZ path")
    parser.add_argument(
        "--padding", type=int, default=12, help="pixels retained outside detected page"
    )
    parser.add_argument("--force", action="store_true", help="replace an existing output")
    parser.add_argument(
        "--replace", action="store_true", help="atomically replace the input CBZ"
    )
    parser.add_argument("--dry-run", action="store_true", help="report crops only")
    args = parser.parse_args()

    if args.padding < 0:
        parser.error("--padding must be zero or greater")
    if args.replace and args.output is not None:
        parser.error("--replace and --output cannot be used together")

    source = args.cbz.resolve()
    output = source if args.replace else (args.output or _default_output(source))
    changed, total = crop_cbz(
        source,
        output,
        padding=args.padding,
        force=args.force or args.replace,
        dry_run=args.dry_run,
    )
    action = "would crop" if args.dry_run else "cropped"
    print(f"{action} {changed}/{total} pages")
    if not args.dry_run:
        print(f"output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
