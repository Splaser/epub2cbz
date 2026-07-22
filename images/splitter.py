# images/splitter.py
import os
import re
from typing import List

import numpy as np
from PIL import Image
from utils.consts import ROTATE_DEGREE, ROTATE_VERTICAL_SPLIT_PAGE, ENABLE_SPLIT_WIDE, IMG_EXT

try:
    import cv2
except Exception:
    cv2 = None


_ROTATE_TAG_CACHE: dict[str, dict[str, int]] = {}


def _epub_root_for_image(img_path: str) -> str | None:
    parent = os.path.dirname(os.path.abspath(img_path))
    if not parent:
        return None
    root = os.path.dirname(parent)
    try:
        if (
            os.path.isdir(os.path.join(root, "META-INF"))
            or os.path.isdir(os.path.join(root, "html"))
            or any(name.lower().endswith(".opf") for name in os.listdir(root))
        ):
            return root
    except OSError:
        pass
    return None


def _load_epub_rotate_tags(root_dir: str) -> dict[str, int]:
    cached = _ROTATE_TAG_CACHE.get(root_dir)
    if cached is not None:
        return cached

    tags: dict[str, int] = {}
    img_tag_re = re.compile(r"""<img\b[^>]*>""", re.IGNORECASE)
    src_re = re.compile(r"""\bsrc=["']([^"']+\.(?:jpe?g|png|webp|gif))["']""", re.IGNORECASE)
    rotate_re = re.compile(r"""\bkmoetag=["'][^"']*rotate:(\d+)""", re.IGNORECASE)

    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if not filename.lower().endswith((".html", ".htm", ".xhtml")):
                continue
            path = os.path.join(dirpath, filename)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue

            for tag_match in img_tag_re.finditer(text):
                tag = tag_match.group(0)
                src_match = src_re.search(tag)
                rotate_match = rotate_re.search(tag)
                if src_match is None or rotate_match is None:
                    continue
                tags[os.path.basename(src_match.group(1))] = int(rotate_match.group(1))

    _ROTATE_TAG_CACHE[root_dir] = tags
    return tags


def get_epub_rotate_hint(img_path: str) -> int | None:
    root_dir = _epub_root_for_image(img_path)
    if root_dir is None or not os.path.isdir(root_dir):
        return None

    tags = _load_epub_rotate_tags(root_dir)
    return tags.get(os.path.basename(img_path))


def should_allow_tb_split_by_rotated_text_flow(im: Image.Image, split_y: int) -> bool:
    if cv2 is None:
        return False

    w, h = im.size
    top = im.crop((0, 0, w, split_y))
    bottom = im.crop((0, split_y, w, h))
    top, bottom = maybe_rotate_split_parts(top, bottom)

    for part in (top, bottom):
        horizontal_flow, vertical_flow, total = _text_flow_score(part)
        if total >= 8 and vertical_flow >= 8 and vertical_flow >= horizontal_flow * 1.15:
            return True

    return False


def has_clean_horizontal_separator(im: Image.Image, split_y: int) -> bool:
    """
    Verify that a horizontal split candidate is a clean page separator, not just
    a panel gutter. Real page separators should stay bright and low-ink across a
    small band; panel rows usually contain frames, art, or lettering nearby.
    """
    w, h = im.size
    if split_y <= 0 or split_y >= h:
        return False

    gray = np.asarray(im.convert("L"))
    half_h = max(6, int(h * 0.004))
    y0 = max(0, split_y - half_h)
    y1 = min(h, split_y + half_h + 1)
    x0 = int(w * 0.035)
    x1 = int(w * 0.965)
    band = gray[y0:y1, x0:x1]
    if band.size == 0:
        return False

    white_ratio = float((band >= 245).mean())
    dark_ratio = float((band <= 80).mean())
    if white_ratio < 0.76 or dark_ratio > 0.11:
        return False

    band_count = 15
    band_w = max(1, band.shape[1] // band_count)
    clean_bands = 0
    for i in range(band_count):
        bx0 = i * band_w
        bx1 = band.shape[1] if i == band_count - 1 else (i + 1) * band_w
        local = band[:, bx0:bx1]
        if local.size == 0:
            continue
        local_white = float((local >= 245).mean())
        local_dark = float((local <= 80).mean())
        if local_white >= 0.72 and local_dark <= 0.12:
            clean_bands += 1

    return clean_bands >= 10


def has_relaxed_horizontal_separator(im: Image.Image, split_y: int) -> bool:
    """
    Looser separator check for EPUB pages explicitly marked as rotated.
    Chapter/title spreads can put logo text over the center gutter, so the strict
    clean-band check may reject them even though the gutter is real.
    """
    w, h = im.size
    if split_y <= 0 or split_y >= h:
        return False

    gray = np.asarray(im.convert("L"))
    half_h = max(6, int(h * 0.005))
    y0 = max(0, split_y - half_h)
    y1 = min(h, split_y + half_h + 1)
    x0 = int(w * 0.035)
    x1 = int(w * 0.965)
    band = gray[y0:y1, x0:x1]
    if band.size == 0:
        return False

    white_ratio = float((band >= 242).mean())
    dark_ratio = float((band <= 80).mean())
    if white_ratio < 0.68 or dark_ratio > 0.08:
        return False

    band_count = 15
    band_w = max(1, band.shape[1] // band_count)
    usable_bands = 0
    for i in range(band_count):
        bx0 = i * band_w
        bx1 = band.shape[1] if i == band_count - 1 else (i + 1) * band_w
        local = band[:, bx0:bx1]
        if local.size == 0:
            continue
        local_white = float((local >= 242).mean())
        local_dark = float((local <= 80).mean())
        if local_white >= 0.56 and local_dark <= 0.13:
            usable_bands += 1

    return usable_bands >= 9

# --- New function for horizontal gutter detection ---
def find_horizontal_gutter_y_cv(im: Image.Image) -> int | None:
    """
    CV-based horizontal gutter detector.
    It combines color distribution with line direction: a valid split line should be
    a bright, low-ink, near-horizontal corridor close to the page center.
    """
    if cv2 is None:
        return None

    w, h = im.size
    if w < 800 or h < 500:
        return None

    gray = np.asarray(im.convert("L"))

    # Strict position: only inspect the central horizontal area.
    y0 = int(h * 0.43)
    y1 = int(h * 0.57)
    x0 = int(w * 0.03)
    x1 = int(w * 0.97)
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0:
        return None

    # Smooth tiny print noise, then measure white/dark distribution by row.
    blur = cv2.GaussianBlur(roi, (5, 5), 0)
    white_ratio = (blur >= 238).mean(axis=1)
    dark_ratio = (blur <= 80).mean(axis=1)
    row_score = white_ratio - dark_ratio * 1.55

    best_local_y = int(np.argmax(row_score))
    if white_ratio[best_local_y] < 0.78 or dark_ratio[best_local_y] > 0.12:
        return None

    # Direction check: the candidate corridor must be almost horizontal.
    # Build edges from non-white ink near the center area, then look for long
    # horizontal line segments around the candidate y.
    ink = cv2.threshold(blur, 210, 255, cv2.THRESH_BINARY_INV)[1]
    edges = cv2.Canny(ink, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=max(60, w // 30),
        minLineLength=max(80, w // 12),
        maxLineGap=max(12, w // 80),
    )

    if lines is not None:
        near_horizontal_count = 0
        diagonal_or_vertical_nearby = 0
        for line in lines[:, 0, :]:
            x_a, y_a, x_b, y_b = map(int, line)
            dx = x_b - x_a
            dy = y_b - y_a
            length = float(np.hypot(dx, dy))
            if length < max(80, w * 0.06):
                continue
            angle = abs(np.degrees(np.arctan2(dy, dx)))
            angle = min(angle, 180.0 - angle)
            line_y = (y_a + y_b) / 2.0
            if abs(line_y - best_local_y) <= max(8, int(h * 0.008)):
                if angle <= 2.0:
                    near_horizontal_count += 1
                elif angle >= 8.0:
                    diagonal_or_vertical_nearby += 1

        if diagonal_or_vertical_nearby > near_horizontal_count + 2:
            return None

    # Continuity check: split the row into bands and require most bands to agree.
    band_count = 13
    band_w = roi.shape[1] // band_count
    centers: list[int] = []
    tolerance = max(5, int(h * 0.005))
    r0 = max(0, best_local_y - tolerance)
    r1 = min(roi.shape[0], best_local_y + tolerance + 1)
    for i in range(band_count):
        bx0 = i * band_w
        bx1 = roi.shape[1] if i == band_count - 1 else (i + 1) * band_w
        local = blur[r0:r1, bx0:bx1]
        if local.size == 0:
            continue
        local_white = (local >= 238).mean(axis=1)
        local_dark = (local <= 80).mean(axis=1)
        local_score = local_white - local_dark * 1.35
        local_best = int(np.argmax(local_score)) + r0
        if local_white[local_best - r0] >= 0.55 and local_dark[local_best - r0] <= 0.24:
            centers.append(local_best)

    if len(centers) < 10:
        return None

    if max(centers) - min(centers) > max(8, int(h * 0.007)):
        return None

    gutter_y = y0 + int(round(float(np.median(centers))))
    if not (h * 0.47 <= gutter_y <= h * 0.53):
        return None

    return gutter_y


# --- Helper: Detect vertical text near a horizontal split candidate ---
def has_vertical_text_near_horizontal_split(im: Image.Image, split_y: int) -> bool:
    """
    Conservative guard for rotated single pages.
    If the candidate horizontal split area contains many vertical text-like dark
    components, it is probably an inner manga panel gutter rather than a true
    two-page separator. In that case, keep the image as a single page.
    """
    if cv2 is None:
        return False

    w, h = im.size
    if w < 800 or h < 500:
        return False

    gray = np.asarray(im.convert("L"))
    band_half_h = max(36, int(h * 0.055))
    y0 = max(0, split_y - band_half_h)
    y1 = min(h, split_y + band_half_h)
    x0 = int(w * 0.08)
    x1 = int(w * 0.92)
    band = gray[y0:y1, x0:x1]
    if band.size == 0:
        return False

    # Text is dark and compact. Avoid counting huge panel borders/SFX strokes by
    # filtering component geometry and area.
    ink = cv2.threshold(band, 120, 255, cv2.THRESH_BINARY_INV)[1]
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)

    vertical_like = 0
    total_text_like = 0
    for label in range(1, num_labels):
        x, y, bw, bh, area = stats[label]
        if area < 8 or area > band.size * 0.015:
            continue
        if bw < 2 or bh < 4:
            continue
        # Ignore long frame lines and giant SFX chunks.
        if bw > w * 0.10 or bh > h * 0.12:
            continue

        aspect = bh / max(1, bw)
        fill = area / max(1, bw * bh)
        if 0.12 <= fill <= 0.75:
            total_text_like += 1
            if aspect >= 1.6:
                vertical_like += 1

    if total_text_like < 10:
        return False

    vertical_ratio = vertical_like / max(1, total_text_like)
    return vertical_like >= 8 and vertical_ratio >= 0.45


def is_image_file(path: str) -> bool:
    return path.lower().endswith(IMG_EXT)


def should_skip_by_filename(path: str) -> bool:
    name = os.path.splitext(os.path.basename(path).lower())[0]
    exact_names = {"end", "ad", "ads", "adv", "advertisement", "copyright", "backcover", "afterword"}
    if name in exact_names:
        return True

    return any(name.endswith(f"_{suffix}") or name.endswith(f"-{suffix}") for suffix in exact_names)


def save_image_part(im: Image.Image, path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext in [".jpg", ".jpeg"] and im.mode not in ["RGB", "L"]:
        im = im.convert("RGB")
    im.save(path)


def _save_tb_split(im: Image.Image, split_y: int, out_dir: str, base: str, ext: str) -> list[str]:
    w, h = im.size
    top = im.crop((0, 0, w, split_y))
    bottom = im.crop((0, split_y, w, h))
    top, bottom = maybe_rotate_split_parts(top, bottom)

    top_path = os.path.join(out_dir, f"{base}__TOP{ext}")
    bottom_path = os.path.join(out_dir, f"{base}__BOTTOM{ext}")
    save_image_part(top, top_path)
    save_image_part(bottom, bottom_path)
    return [top_path, bottom_path]


def _save_lr_split(im: Image.Image, split_x: int, out_dir: str, base: str, ext: str) -> list[str]:
    w, h = im.size
    left = im.crop((0, 0, split_x, h))
    right = im.crop((split_x, 0, w, h))
    left, right = maybe_rotate_split_parts(left, right)

    left_path = os.path.join(out_dir, f"{base}__L{ext}")
    right_path = os.path.join(out_dir, f"{base}__R{ext}")
    save_image_part(left, left_path)
    save_image_part(right, right_path)
    return [right_path, left_path]


def rotate_split_part(im: Image.Image) -> Image.Image:
    """Rotate every page part produced by a top/bottom split."""
    return im.rotate(ROTATE_DEGREE, expand=True)


# --- Helper to rotate all split parts if needed ---
def maybe_rotate_split_parts(*parts: Image.Image) -> tuple[Image.Image, ...]:
    """Apply the configured split-page rotation to every generated split part."""
    if not ROTATE_VERTICAL_SPLIT_PAGE:
        return parts
    return tuple(rotate_split_part(part) for part in parts)

# --- Helper: Guard against cutting a rotated single page through the waist ---
def should_skip_tb_split_by_part_ratio(im: Image.Image, split_y: int) -> bool:
    """
    Guard against cutting a rotated single page through the waist.
    For a real TB split, each generated part should still look like a plausible
    full manga page after the configured split rotation. If both parts become
    extremely narrow/short half-page fragments, the detected center line is more
    likely an internal panel gutter.
    """
    w, h = im.size
    top_h = split_y
    bottom_h = h - split_y
    if top_h <= 0 or bottom_h <= 0:
        return True

    def normalized_ratio(part_w: int, part_h: int) -> float:
        a = min(part_w, part_h)
        b = max(part_w, part_h)
        return a / max(1, b)

    if ROTATE_VERTICAL_SPLIT_PAGE:
        # After TB split, parts are rotated, so dimensions swap.
        top_ratio = normalized_ratio(top_h, w)
        bottom_ratio = normalized_ratio(bottom_h, w)
    else:
        top_ratio = normalized_ratio(w, top_h)
        bottom_ratio = normalized_ratio(w, bottom_h)

    # Normal manga pages are usually around 0.62~0.78. A waist-cut rotated page
    # often produces fragments around 0.25~0.50. Be conservative: only reject
    # when both parts are fragment-like.
    return top_ratio < 0.55 and bottom_ratio < 0.55


# --- Helper: Guard against TB split when both parts look sideways after rotation ---

def _text_orientation_score(im: Image.Image) -> tuple[int, int, int]:
    """Return (vertical_like, horizontal_like, total_text_like) for compact text components."""
    if cv2 is None:
        return 0, 0, 0

    w, h = im.size
    if w < 120 or h < 120:
        return 0, 0, 0

    gray = np.asarray(im.convert("L"))
    x0 = int(w * 0.04)
    x1 = int(w * 0.96)
    y0 = int(h * 0.04)
    y1 = int(h * 0.96)
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0:
        return 0, 0, 0

    ink = cv2.threshold(roi, 135, 255, cv2.THRESH_BINARY_INV)[1]
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)

    vertical_like = 0
    horizontal_like = 0
    total_text_like = 0
    for label in range(1, num_labels):
        _, _, bw, bh, area = stats[label]
        if area < 8 or area > roi.size * 0.012:
            continue
        if bw < 2 or bh < 3:
            continue
        if bw > w * 0.16 or bh > h * 0.22:
            continue

        fill = area / max(1, bw * bh)
        if not (0.10 <= fill <= 0.80):
            continue

        aspect = bh / max(1, bw)
        total_text_like += 1
        if aspect >= 1.45:
            vertical_like += 1
        elif aspect <= 0.70:
            horizontal_like += 1

    return vertical_like, horizontal_like, total_text_like


# --- New helpers: text component analysis and flow ---
def _text_component_boxes(im: Image.Image) -> list[tuple[int, int, int, int]]:
    """Return compact text-like component boxes as (x, y, w, h)."""
    if cv2 is None:
        return []

    w, h = im.size
    if w < 120 or h < 120:
        return []

    gray = np.asarray(im.convert("L"))
    x0 = int(w * 0.04)
    x1 = int(w * 0.96)
    y0 = int(h * 0.04)
    y1 = int(h * 0.96)
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0:
        return []

    ink = cv2.threshold(roi, 145, 255, cv2.THRESH_BINARY_INV)[1]
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)

    boxes: list[tuple[int, int, int, int]] = []
    for label in range(1, num_labels):
        x, y, bw, bh, area = stats[label]
        if area < 8 or area > roi.size * 0.010:
            continue
        if bw < 2 or bh < 3:
            continue
        if bw > w * 0.13 or bh > h * 0.18:
            continue

        fill = area / max(1, bw * bh)
        if not (0.08 <= fill <= 0.82):
            continue

        boxes.append((int(x + x0), int(y + y0), int(bw), int(bh)))

    return boxes


def _text_flow_score(im: Image.Image) -> tuple[int, int, int]:
    """
    Return (horizontal_flow, vertical_flow, component_count).
    This estimates the writing system by local component alignment instead of
    individual glyph aspect ratio. Sideways vertical Chinese tends to form
    horizontal runs after the wrong rotation; normal manga text tends to form
    vertical runs/columns.
    """
    boxes = _text_component_boxes(im)
    if len(boxes) < 8:
        return 0, 0, len(boxes)

    centers = []
    sizes = []
    for x, y, bw, bh in boxes:
        centers.append((x + bw / 2.0, y + bh / 2.0))
        sizes.append(max(4.0, (bw + bh) / 2.0))

    horizontal_flow = 0
    vertical_flow = 0
    n = len(centers)
    for i in range(n):
        cx, cy = centers[i]
        size_i = sizes[i]
        for j in range(i + 1, n):
            ox, oy = centers[j]
            size = max(size_i, sizes[j])
            dx = abs(ox - cx)
            dy = abs(oy - cy)

            # Same row, neighboring glyphs.
            if dy <= size * 0.70 and size * 0.45 <= dx <= size * 3.20:
                horizontal_flow += 1

            # Same column, neighboring glyphs.
            if dx <= size * 0.70 and size * 0.45 <= dy <= size * 3.20:
                vertical_flow += 1

    return horizontal_flow, vertical_flow, n


def _punctuation_direction_score(im: Image.Image) -> tuple[int, int, int]:
    """
    Return (horizontal_marks, vertical_marks, mark_count) for comma/ellipsis-like
    tiny marks. This is intentionally conservative and only acts as an auxiliary
    signal: CJK ellipses and punctuation dots tend to align with the text flow,
    so a wrongly rotated page often flips these marks from vertical to horizontal.
    """
    if cv2 is None:
        return 0, 0, 0

    w, h = im.size
    if w < 120 or h < 120:
        return 0, 0, 0

    gray = np.asarray(im.convert("L"))
    x0 = int(w * 0.04)
    x1 = int(w * 0.96)
    y0 = int(h * 0.04)
    y1 = int(h * 0.96)
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0:
        return 0, 0, 0

    ink = cv2.threshold(roi, 155, 255, cv2.THRESH_BINARY_INV)[1]
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)

    marks: list[tuple[float, float, float, int]] = []
    max_dim = max(10, int(min(w, h) * 0.018))
    max_area = max(70, int(roi.size * 0.00018))
    for label in range(1, num_labels):
        x, y, bw, bh, area = stats[label]
        if area < 5 or area > max_area:
            continue
        if bw < 2 or bh < 2 or bw > max_dim or bh > max_dim:
            continue

        fill = area / max(1, bw * bh)
        if not (0.20 <= fill <= 0.92):
            continue

        aspect = max(bw, bh) / max(1, min(bw, bh))
        if aspect > 2.6:
            continue

        marks.append((x + x0 + bw / 2.0, y + y0 + bh / 2.0, float(max(bw, bh)), int(area)))

    if len(marks) < 6:
        return 0, 0, len(marks)

    horizontal_marks = 0
    vertical_marks = 0
    n = len(marks)
    for i in range(n):
        cx, cy, size_i, area_i = marks[i]
        for j in range(i + 1, n):
            ox, oy, size_j, area_j = marks[j]
            size = max(4.0, size_i, size_j)
            area_ratio = max(area_i, area_j) / max(1, min(area_i, area_j))
            if area_ratio > 3.0:
                continue

            dx = abs(ox - cx)
            dy = abs(oy - cy)
            if dy <= size * 0.70 and size * 0.70 <= dx <= size * 4.8:
                horizontal_marks += 1
            if dx <= size * 0.70 and size * 0.70 <= dy <= size * 4.8:
                vertical_marks += 1

    return horizontal_marks, vertical_marks, len(marks)


def should_skip_tb_split_by_text_direction(im: Image.Image, split_y: int) -> bool:
    """
    After a TB split, simulate the configured output rotation and check whether
    detected text components still look sideways. If so, the split is probably
    an internal panel gutter rather than a real two-page separator.
    """
    if cv2 is None:
        return False

    w, h = im.size
    if split_y <= 0 or split_y >= h:
        return True

    top = im.crop((0, 0, w, split_y))
    bottom = im.crop((0, split_y, w, h))
    top, bottom = maybe_rotate_split_parts(top, bottom)

    punctuation_scores = [_punctuation_direction_score(top), _punctuation_direction_score(bottom)]
    punctuation_parts = [s for s in punctuation_scores if s[2] >= 10]
    punctuation_sideways_parts = 0
    punctuation_readable_parts = 0
    for horizontal_marks, vertical_marks, mark_count in punctuation_parts:
        if horizontal_marks >= 18 and horizontal_marks >= vertical_marks * 1.45:
            punctuation_sideways_parts += 1
        if vertical_marks >= 18 and vertical_marks >= horizontal_marks * 1.25:
            punctuation_readable_parts += 1

    if punctuation_sideways_parts >= 1 and punctuation_readable_parts == 0:
        return True

    # First judge the writing flow by component alignment. This is more reliable
    # for Chinese/Japanese text than glyph aspect ratio because many glyphs are
    # close to square. If the split+rotation makes text form horizontal rows,
    # the original page was probably already a rotated single page, not a TB spread.
    flow_scores = [_text_flow_score(top), _text_flow_score(bottom)]
    flow_parts = [s for s in flow_scores if s[2] >= 8]
    horizontal_flow_parts = 0
    vertical_flow_parts = 0
    strong_horizontal_parts = 0
    for horizontal_flow, vertical_flow, total in flow_parts:
        # After a valid TB split + configured rotation, Chinese/Japanese manga text
        # should not mainly form horizontal rows. If it does, the split likely cut
        # a rotated single page through an internal panel gutter.
        if horizontal_flow >= 8 and horizontal_flow >= vertical_flow * 1.10:
            horizontal_flow_parts += 1
        if horizontal_flow >= 12 and horizontal_flow >= vertical_flow * 1.35:
            strong_horizontal_parts += 1
        if vertical_flow >= 8 and vertical_flow >= horizontal_flow * 1.15:
            vertical_flow_parts += 1

    if flow_parts and strong_horizontal_parts >= 1:
        return True
    if len(flow_parts) >= 2 and horizontal_flow_parts >= vertical_flow_parts:
        return True
    if len(flow_parts) == 1 and horizontal_flow_parts == 1 and vertical_flow_parts == 0:
        return True

    scores = [_text_orientation_score(top), _text_orientation_score(bottom)]
    text_parts = [s for s in scores if s[2] >= 10]
    if not text_parts:
        return False

    readable_parts = 0
    sideways_parts = 0
    for vertical_like, horizontal_like, total in text_parts:
        vertical_ratio = vertical_like / max(1, total)
        horizontal_ratio = horizontal_like / max(1, total)
        if vertical_like >= 6 and vertical_ratio >= 0.34 and vertical_like >= horizontal_like:
            readable_parts += 1
        if horizontal_like >= 8 and horizontal_ratio >= 0.38 and horizontal_like > vertical_like * 1.2:
            sideways_parts += 1

    return sideways_parts >= 1 and readable_parts == 0

def should_skip_tb_split_by_original_text_flow(im: Image.Image) -> bool:
    """
    Reject TB split before cutting when the whole image already has a strong
    horizontal text flow. That usually means the source is one rotated manga page,
    not two stacked pages.
    """
    if cv2 is None:
        return False

    horizontal_flow, vertical_flow, total = _text_flow_score(im)
    if total < 12:
        return False

    return horizontal_flow >= 14 and horizontal_flow >= vertical_flow * 1.25


# --- Helper functions for gutter detection ---

def _longest_true_run(mask: np.ndarray) -> tuple[int | None, int | None]:
    """Return [start, end) of the longest True run."""
    best_start = None
    best_end = None
    cur_start = None

    for i, v in enumerate(mask.tolist()):
        if v and cur_start is None:
            cur_start = i
        elif not v and cur_start is not None:
            if best_start is None or i - cur_start > best_end - best_start:
                best_start, best_end = cur_start, i
            cur_start = None

    if cur_start is not None:
        i = len(mask)
        if best_start is None or i - cur_start > best_end - best_start:
            best_start, best_end = cur_start, i

    return best_start, best_end

def _find_gutter_center_in_band(band: np.ndarray) -> int | None:
    """Find a strict white gutter center inside one horizontal band."""
    white_ratio = (band >= 248).mean(axis=0)
    dark_ratio = (band <= 80).mean(axis=0)
    candidate = (white_ratio >= 0.96) & (dark_ratio <= 0.015)

    start, end = _longest_true_run(candidate)
    if start is None or end is None:
        return None

    return (start + end) // 2


def find_vertical_gutter_x(im: Image.Image) -> int | None:
    """
    Detect a clear white vertical gutter near the middle of a double-page scan.
    This is more reliable than blindly splitting at w//2 when the two pages are
    separated by an obvious white binding line but the scan is slightly offset.
    """
    w, h = im.size
    if w < 800 or h < 600:
        return None

    gray = im.convert("L")
    arr = np.asarray(gray)

    # Only search very close to the expected book gutter.
    # Keep this strict to avoid treating panel borders/speech bubbles as page gutters.
    x0 = int(w * 0.44)
    x1 = int(w * 0.56)
    if x1 <= x0:
        return None

    # Ignore outer top/bottom margins where white background can dominate.
    y0 = int(h * 0.10)
    y1 = int(h * 0.90)
    mid = arr[y0:y1, x0:x1]

    # A gutter column is bright and has very little dark ink across most rows.
    white_ratio = (mid >= 248).mean(axis=0)
    dark_ratio = (mid <= 80).mean(axis=0)
    candidate = (white_ratio >= 0.95) & (dark_ratio <= 0.015)

    start, end = _longest_true_run(candidate)
    if start is None or end is None:
        return None

    run_width = end - start
    min_width = max(6, int(w * 0.005))
    max_width = max(48, int(w * 0.045))
    if run_width < min_width or run_width > max_width:
        return None

    gutter_center = (start + end) // 2

    # Validate the gutter as a nearly straight vertical line by checking several
    # horizontal bands. If the detected x position drifts too much, it is likely
    # a panel edge, diagonal drawing element, or scan artifact rather than a page gutter.
    band_count = 5
    band_h = mid.shape[0] // band_count
    centers: list[int] = []
    for i in range(band_count):
        by0 = i * band_h
        by1 = mid.shape[0] if i == band_count - 1 else (i + 1) * band_h
        center = _find_gutter_center_in_band(mid[by0:by1, :])
        if center is None:
            continue
        if abs(center - gutter_center) <= max(4, int(w * 0.0025)):
            centers.append(center)

    if len(centers) < 4:
        return None

    max_drift = max(centers) - min(centers)
    if max_drift > max(6, int(w * 0.0035)):
        return None

    gutter_x = x0 + int(round(float(np.median(centers))))

    # Avoid accidental split lines that are too far away from the page center.
    if not (w * 0.46 <= gutter_x <= w * 0.54):
        return None

    return gutter_x


# --- New function for horizontal gutter detection ---
def find_horizontal_gutter_y(im: Image.Image) -> int | None:
    """
    Detect a clear white horizontal gutter near the middle of a rotated double-page scan.
    Some double-page scans are stored sideways, so the real page separator appears
    as a long horizontal white line instead of a vertical center gutter.
    """
    w, h = im.size
    if w < 800 or h < 500:
        return None

    gray = im.convert("L")
    arr = np.asarray(gray)

    # Only search very close to the expected horizontal center line.
    y0 = int(h * 0.42)
    y1 = int(h * 0.58)
    if y1 <= y0:
        return None

    # Ignore only a small left/right margin. Manga center gutters often contain
    # SFX/text interruptions, so using too narrow a crop makes the row score unstable.
    x0 = int(w * 0.04)
    x1 = int(w * 0.96)
    mid = arr[y0:y1, x0:x1]

    # A horizontal page gutter should be mostly white, but not necessarily pure white
    # across the whole row because speech bubbles/SFX can cross the center line.
    white_ratio = (mid >= 242).mean(axis=1)
    dark_ratio = (mid <= 80).mean(axis=1)
    candidate = (white_ratio >= 0.78) & (dark_ratio <= 0.12)

    start, end = _longest_true_run(candidate)
    if start is None or end is None:
        return None

    run_height = end - start
    min_height = max(3, int(h * 0.003))
    max_height = max(48, int(h * 0.070))
    if run_height < min_height or run_height > max_height:
        return None

    gutter_center = (start + end) // 2

    # Validate the gutter as a nearly straight horizontal line by checking many
    # vertical bands. Use local rows around the global gutter center instead of
    # requiring each band to be pure white across its whole width; otherwise SFX
    # and speech bubbles crossing the gutter make real double-pages fail.
    band_count = 11
    band_w = mid.shape[1] // band_count
    centers: list[int] = []
    tolerance = max(4, int(h * 0.0045))
    local_r0 = max(0, gutter_center - tolerance)
    local_r1 = min(mid.shape[0], gutter_center + tolerance + 1)
    for i in range(band_count):
        bx0 = i * band_w
        bx1 = mid.shape[1] if i == band_count - 1 else (i + 1) * band_w
        local = mid[local_r0:local_r1, bx0:bx1]
        local_white_ratio = (local >= 242).mean(axis=1)
        local_dark_ratio = (local <= 80).mean(axis=1)
        local_score = local_white_ratio - local_dark_ratio * 1.5
        if local_score.size == 0:
            continue
        local_best = int(np.argmax(local_score)) + local_r0
        if local_white_ratio[local_best - local_r0] >= 0.62 and local_dark_ratio[local_best - local_r0] <= 0.20:
            centers.append(local_best)

    if len(centers) < 8:
        return None

    max_drift = max(centers) - min(centers)
    if max_drift > max(7, int(h * 0.006)):
        return None

    gutter_y = y0 + int(round(float(np.median(centers))))

    # Keep position strict: this should be the central page separator, not an inner panel border.
    if not (h * 0.47 <= gutter_y <= h * 0.53):
        return None

    return gutter_y


def find_clean_horizontal_gutter_y(im: Image.Image) -> tuple[int | None, str, int | None]:
    """
    Try horizontal gutter detectors in order and keep the first candidate that
    also passes the clean separator check. Returns (y, reason, rejected_y).
    """
    rejected_y: int | None = None
    seen: set[int] = set()
    candidates: list[tuple[str, int]] = []

    cv_y = find_horizontal_gutter_y_cv(im)
    if cv_y is not None:
        candidates.append(("cv", cv_y))
        seen.add(cv_y)

    projection_y = find_horizontal_gutter_y(im)
    if projection_y is not None and projection_y not in seen:
        candidates.append(("projection", projection_y))

    for reason, split_y in candidates:
        if has_clean_horizontal_separator(im, split_y):
            return split_y, reason, rejected_y
        if rejected_y is None:
            rejected_y = split_y

    return None, "projection", rejected_y


def has_vertical_text_layout(im: Image.Image) -> bool:
    """
    Guard for rotated normal manga pages.
    A real horizontal page separator should not be decided only by a center panel
    border. If the whole image contains enough vertical-text-like components,
    treat the center horizontal line as an internal panel gutter and skip TB split.
    """
    if cv2 is None:
        return False

    horizontal_flow, vertical_flow, flow_total = _text_flow_score(im)
    if flow_total >= 12 and vertical_flow >= 10 and vertical_flow >= horizontal_flow * 1.20:
        return True

    w, h = im.size
    if w < 700 or h < 450:
        return False

    gray = np.asarray(im.convert("L"))
    x0 = int(w * 0.05)
    x1 = int(w * 0.95)
    y0 = int(h * 0.05)
    y1 = int(h * 0.95)
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0:
        return False

    ink = cv2.threshold(roi, 135, 255, cv2.THRESH_BINARY_INV)[1]
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)

    vertical_like = 0
    horizontal_like = 0
    total_text_like = 0
    for label in range(1, num_labels):
        x, y, bw, bh, area = stats[label]
        if area < 10 or area > roi.size * 0.010:
            continue
        if bw < 2 or bh < 3:
            continue
        if bw > w * 0.12 or bh > h * 0.18:
            continue

        fill = area / max(1, bw * bh)
        if not (0.10 <= fill <= 0.78):
            continue

        aspect = bh / max(1, bw)
        total_text_like += 1
        if aspect >= 1.45:
            vertical_like += 1
        elif aspect <= 0.70:
            horizontal_like += 1

    if total_text_like < 18:
        return False

    vertical_ratio = vertical_like / max(1, total_text_like)
    return vertical_like >= 12 and vertical_ratio >= 0.38 and vertical_like >= horizontal_like * 1.15


def infer_common_page_size(image_paths: List[str]) -> tuple[int, int] | None:
    """Infer the dominant original page size in one book, allowing scan jitter."""
    groups: list[list[tuple[int, int]]] = []
    checked = 0
    for path in image_paths:
        if not is_image_file(path):
            continue
        try:
            with Image.open(path) as im:
                w, h = im.size
        except Exception:
            continue

        if w < 300 or h < 300:
            continue
        checked += 1

        placed = False
        for group in groups:
            gw = int(round(float(np.median([size[0] for size in group]))))
            gh = int(round(float(np.median([size[1] for size in group]))))
            if abs(w - gw) <= max(10, int(gw * 0.035)) and abs(h - gh) <= max(10, int(gh * 0.035)):
                group.append((w, h))
                placed = True
                break

        if not placed:
            groups.append([(w, h)])

    if checked < 6 or not groups:
        return None

    group = max(groups, key=len)
    if len(group) < max(6, int(checked * 0.20)):
        return None

    ws = sorted(size[0] for size in group)
    hs = sorted(size[1] for size in group)
    return int(round(float(np.median(ws)))), int(round(float(np.median(hs))))


def _matches_common_page_size(
    w: int,
    h: int,
    common_page_size: tuple[int, int] | None,
    tolerance_ratio: float = 0.04,
) -> bool:
    if common_page_size is None:
        return False

    cw, ch = common_page_size
    if cw <= 0 or ch <= 0:
        return False

    return abs(w - cw) <= max(8, int(cw * tolerance_ratio)) and abs(h - ch) <= max(
        8,
        int(ch * tolerance_ratio),
    )


def _tb_split_parts_match_common_page_size(
    im: Image.Image,
    split_y: int,
    common_page_size: tuple[int, int] | None,
) -> bool:
    if common_page_size is None:
        return False

    w, h = im.size
    if split_y <= 0 or split_y >= h:
        return False

    top_h = split_y
    bottom_h = h - split_y
    if ROTATE_VERTICAL_SPLIT_PAGE:
        top_w, top_h = top_h, w
        bottom_w, bottom_h = bottom_h, w
    else:
        top_w, bottom_w = w, w

    top_matches = _matches_common_page_size(
        top_w,
        top_h,
        common_page_size,
        tolerance_ratio=0.04,
    )
    bottom_matches = _matches_common_page_size(
        bottom_w,
        bottom_h,
        common_page_size,
        tolerance_ratio=0.04,
    )
    return top_matches and bottom_matches


def _tb_split_parts_match_common_aspect(
    im: Image.Image,
    split_y: int,
    common_page_size: tuple[int, int] | None,
) -> bool:
    if common_page_size is None:
        return False

    cw, ch = common_page_size
    if cw <= 0 or ch <= 0:
        return False

    w, h = im.size
    if split_y <= 0 or split_y >= h:
        return False

    common_ratio = min(cw, ch) / max(cw, ch)
    part_dims = [(w, split_y), (w, h - split_y)]
    for part_w, part_h in part_dims:
        if ROTATE_VERTICAL_SPLIT_PAGE:
            part_w, part_h = part_h, part_w
        part_ratio = min(part_w, part_h) / max(1, max(part_w, part_h))
        if abs(part_ratio - common_ratio) > 0.04:
            return False

    return True


def _tagged_tb_fallback_y(
    im: Image.Image,
    rotate_hint: int | None,
    common_page_size: tuple[int, int] | None,
) -> int | None:
    """
    Return a conservative center split for EPUB-declared rotated spreads.

    Some Kmoe EPUBs concatenate two pages without leaving a white gutter.  In
    that case pixel-only gutter detection has no candidate at all.  The rotate
    metadata is useful, but is not sufficient by itself because cover wraps and
    promotional foldouts may carry the same tag.  Only accept the fallback when
    both resulting halves have the same aspect ratio as the book's dominant
    single-page size.
    """
    if rotate_hint != 1 or common_page_size is None:
        return None

    _, h = im.size
    split_y = h // 2
    if not _tb_split_parts_match_common_aspect(im, split_y, common_page_size):
        return None

    return split_y


def _tb_pre_split_skip_reason(
    im: Image.Image,
    split_y: int,
    is_common_page_size: bool,
    common_page_size: tuple[int, int] | None,
    rotate_hint: int | None = None,
) -> str | None:
    parts_match_common_page = _tb_split_parts_match_common_page_size(
        im,
        split_y,
        common_page_size,
    )
    parts_match_common_aspect = _tb_split_parts_match_common_aspect(
        im,
        split_y,
        common_page_size,
    )
    has_text_direction_mismatch = should_skip_tb_split_by_text_direction(im, split_y)
    has_original_vertical_layout = has_vertical_text_layout(im)

    if rotate_hint == 0:
        return "epub-rotate-tag"

    if rotate_hint == 1 and parts_match_common_aspect:
        return None

    if common_page_size is not None and not parts_match_common_page and not (
        is_common_page_size and parts_match_common_aspect
    ):
        return "common-page-part-aspect"

    if (
        is_common_page_size
        and not parts_match_common_page
        and not has_text_direction_mismatch
        and not has_original_vertical_layout
    ):
        return "common-page-text-direction"

    has_positive_text_flow = should_allow_tb_split_by_rotated_text_flow(im, split_y)
    if has_positive_text_flow:
        return None

    if should_skip_tb_split_by_original_text_flow(im):
        return "original-text-flow"

    if not parts_match_common_page and has_text_direction_mismatch:
        return "text-direction"

    if should_skip_tb_split_by_part_ratio(im, split_y):
        return "part-ratio"

    if not parts_match_common_page and (
        has_original_vertical_layout or has_vertical_text_near_horizontal_split(im, split_y)
    ):
        return "vertical-text"

    return None


def _stacked_tb_skip_reason(im: Image.Image, split_y: int, split_reason: str) -> str | None:
    if split_reason == "half":
        return None

    if should_allow_tb_split_by_rotated_text_flow(im, split_y):
        return None

    if should_skip_tb_split_by_original_text_flow(im):
        return "original-text-flow"

    if should_skip_tb_split_by_part_ratio(im, split_y):
        return "part-ratio"

    if should_skip_tb_split_by_text_direction(im, split_y):
        return "text-direction"

    if has_vertical_text_layout(im) or has_vertical_text_near_horizontal_split(im, split_y):
        return "vertical-text"

    return None


def split_wide_image_if_needed(
    img_path: str,
    out_dir: str,
    enable_split: bool = ENABLE_SPLIT_WIDE,
    common_page_size: tuple[int, int] | None = None,
) -> List[str]:
    """
    对单张漫画图片拆分：
    - 横置跨页拆成左右两页
    - 上下堆叠拆成上下两页
    - 末页/版权页保护
    """
    if not enable_split:
        return [img_path]

    if should_skip_by_filename(img_path):
        return [img_path]  # 尾页/版权页保护

    try:
        with Image.open(img_path) as im:
            w, h = im.size
            base = os.path.splitext(os.path.basename(img_path))[0]
            ext = os.path.splitext(img_path)[1].lower()
            is_common_page_size = _matches_common_page_size(w, h, common_page_size)
            rotate_hint = get_epub_rotate_hint(img_path)

            # EPUB page splitting is opt-in.  Heuristic-only splitting can turn
            # unusually tall title pages, bonus art, or cover material into two
            # near-square fragments.  Only images explicitly declared as
            # rotated spreads by the EPUB are eligible for splitting.
            if rotate_hint != 1:
                return [img_path]

            # Rotated double-page scans often show the real page separator as a
            # horizontal white gutter. Detect this before the generic ratio rules.
            if w >= 800 and h >= 500:
                split_y, split_reason, rejected_y = find_clean_horizontal_gutter_y(im)
                if split_y is None and rejected_y is not None:
                    if rotate_hint == 1 and has_relaxed_horizontal_separator(im, rejected_y):
                        split_y = rejected_y
                        split_reason = "rotate-tag"

                if split_y is None:
                    tagged_y = _tagged_tb_fallback_y(im, rotate_hint, common_page_size)
                    if tagged_y is not None:
                        split_y = tagged_y
                        split_reason = "rotate-tag-half"
                    elif rejected_y is not None:
                        print(f"  - keep [split-skip:unclean-horizontal-gutter] {base} {w}x{h} y={rejected_y}")

                if split_y is not None:
                    skip_reason = _tb_pre_split_skip_reason(
                        im,
                        split_y,
                        is_common_page_size,
                        common_page_size,
                        rotate_hint=rotate_hint,
                    )
                    if skip_reason is not None:
                        print(f"  - keep [split-skip:{skip_reason}] {base} {w}x{h} y={split_y}")
                        return [img_path]

                    print(f"  - split [wide-TB:gutter-pre:{split_reason}] {base} {w}x{h} y={split_y}")
                    return _save_tb_split(im, split_y, out_dir, base, ext)

            # A rotate tag can also describe a full cover wrap or foldout. If it
            # did not pass the book-level spread-shape check above, do not let it
            # fall through to the generic tall-image half split.
            if rotate_hint == 1:
                print(f"  - keep [split-skip:rotate-tag-nonspread-shape] {base} {w}x{h}")
                return [img_path]

            # 横向拆分：优先识别中间白色装订/分割线，再退回到 w//2
            if w / h >= 1.25:
                if h > w:  # 纵图横置情况
                    im = im.rotate(ROTATE_DEGREE, expand=True)
                    w, h = im.size

                split_x = find_vertical_gutter_x(im)
                if split_x is not None:
                    print(f"  - split [wide-LR:gutter] {base} {w}x{h} x={split_x}")
                    return _save_lr_split(im, split_x, out_dir, base, ext)

                if w / h < 1.35:
                    return [img_path]

                split_x = w // 2
                print(f"  - split [wide-LR:half] {base} {w}x{h} x={split_x}")
                return _save_lr_split(im, split_x, out_dir, base, ext)
            
            # 上下堆叠拆分：优先用真实水平 gutter；找不到时才退回 h//2。
            if h / w >= 1.65 and w >= 400:
                split_y, split_reason, rejected_y = find_clean_horizontal_gutter_y(im)
                if split_y is None and rejected_y is not None:
                    print(f"  - keep [split-skip:unclean-horizontal-gutter] {base} {w}x{h} y={rejected_y}")
                if split_y is None:
                    if h / w < 2.0:
                        return [img_path]
                    split_y = h // 2
                    split_reason = "half"

                skip_reason = _stacked_tb_skip_reason(im, split_y, split_reason)
                if skip_reason is not None:
                    print(f"  - keep [split-skip:{skip_reason}] {base} {w}x{h} y={split_y}")
                    return [img_path]

                print(f"  - split [vertical-TB:{split_reason}] {base} {w}x{h} y={split_y}")
                return _save_tb_split(im, split_y, out_dir, base, ext)

            return [img_path]

    except Exception as e:
        print(f"  - split failed [{base}]: {e}")
        return [img_path]


def split_images_if_needed(image_paths: List[str], out_dir: str) -> List[str]:
    """
    批量拆分图片
    """
    split_images = []
    common_page_size = infer_common_page_size(image_paths)
    for img in image_paths:
        if is_image_file(img):
            split_images.extend(
                split_wide_image_if_needed(
                    img,
                    out_dir,
                    common_page_size=common_page_size,
                )
            )
        else:
            split_images.append(img)
    return split_images
