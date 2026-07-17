import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from contextlib import ExitStack
from typing import List

from PIL import Image

try:
    import fitz
except ImportError:
    fitz = None
else:
    # Damaged scans can emit thousands of MuPDF diagnostics to stderr while a
    # usable page or fallback is still available. Report recovery counts once
    # per book instead of flooding the console.
    fitz.TOOLS.mupdf_display_errors(False)

try:
    import pypdfium2 as pdfium
except ImportError:
    pdfium = None


def clean_pdf_name(name: str) -> str:
    name = re.sub(r'\s+\d+x\d+(?:\.\d+)?\+\d+x\d+(?:\.\d+)?=\d+(?:\.\d+)?', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


_PDF_MAX_ISSUE = 1500
_PDF_PERIODICAL_RE = re.compile(
    r"^(?:(?:vol(?:ume)?\.?|v)\s*)?0*(\d{1,4})(?!\d)"
    r"(?:\s*[~～\-–—]\s*(?:vol(?:ume)?\.?|v)?\s*0*(\d{1,4})(?!\d))?"
    r"(.*)$",
    flags=re.IGNORECASE,
)
_PDF_EMBEDDED_VOLUME_RE = re.compile(
    r"\bvol(?:ume)?\.?\s*0*(?P<issue>\d{1,4})(?!\d)(?P<suffix>.*)$",
    flags=re.IGNORECASE,
)
_PDF_ISSUE_PUBLICATION_RE = re.compile(
    r"^(?P<issue>\d{3,4}(?:\s*[~～\-–—]\s*\d{3,4})?)"
    # Put 10-12 before 1-9 so the regex cannot leave the final month digit in
    # the suffix (e.g. 011 + 1999.10 used to become 0110, then v110).
    # A combined issue may concatenate publication slots, e.g. 2003.2B3A.
    r"\s+\(?(?:19|20)\d{2}\.(?:(?:1[0-2]|0?[1-9])(?:AB|A|B)?)+\)?"
    r"(?P<suffix>.*)$",
    flags=re.IGNORECASE,
)
_PDF_RELEASE_GROUP_SUFFIX_RE = re.compile(
    r"[\s_.-]*(?:full[\s_.-]*)?CRAZ\s*$",
    flags=re.IGNORECASE,
)
_PDF_SPECIAL_LABELS = ("副刊", "增刊", "特刊", "别册", "別冊")
_PDF_SPECIAL_KEYWORDS = _PDF_SPECIAL_LABELS + (
    "图文攻略",
    "圖文攻略",
    "攻略",
    "攻略本",
    "完全攻略",
    "攻略专辑",
    "攻略專輯",
    "典藏",
    "珍藏",
    "纪念",
    "紀念",
    "周年",
    "週年",
    "专门志",
    "专门誌",
    "專門志",
    "專門誌",
    "之书",
    "之書",
    "档案",
    "檔案",
    "大全",
    "特辑",
    "特輯",
    "专辑",
    "專輯",
)
_PDF_MAIN_ISSUE_SUFFIXES = ("补完", "補完")
_PDF_EXPLICIT_VOLUME_PREFIX_RE = re.compile(
    r"^(?:vol(?:ume)?\.?|v)\s*0*(?P<issue>\d{1,4})(?!\d)",
    flags=re.IGNORECASE,
)
_PDF_NUMBERED_ISSUE_PREFIX_RE = re.compile(r"^0*(?P<issue>\d{1,4})(?!\d)")


def _strip_series_prefix(stem: str, series_name: str) -> str:
    prefixes = (
        series_name,
        f"《{series_name}》",
        f"【{series_name}】",
        f"[{series_name}]",
    )
    for prefix in prefixes:
        if stem.casefold().startswith(prefix.casefold()):
            return stem[len(prefix):].lstrip(" -_")
    return stem


def _clean_periodical_suffix(suffix: str, *labels: str) -> str:
    for label in labels:
        suffix = suffix.replace(label, "")
    suffix = re.sub(r"_+", " ", suffix)
    # A counter immediately following the parsed issue number/range belongs to
    # the number itself, not to the human-readable edition note.
    suffix = re.sub(r"^\s*(?:辑|輯|期|册|冊)\s*", "", suffix)
    suffix = re.sub(r"\s+", " ", suffix)
    return suffix.strip(" .·・-_()[]【】")


def build_pdf_output_cbz_name(pdf_path: str) -> str:
    """Build a Kavita-friendly filename for periodical PDFs."""
    stem = clean_pdf_name(os.path.splitext(os.path.basename(pdf_path))[0])
    series_name = os.path.basename(os.path.dirname(os.path.abspath(pdf_path))).strip()
    if not series_name:
        return f"{stem}.cbz"

    periodical_name = _strip_series_prefix(stem, series_name)
    embedded_volume = _PDF_EMBEDDED_VOLUME_RE.search(periodical_name)
    if embedded_volume is not None:
        issue = int(embedded_volume.group("issue"))
        if issue <= _PDF_MAX_ISSUE:
            periodical_name = f"{issue:03d}" + embedded_volume.group("suffix")

    periodical_name = _PDF_RELEASE_GROUP_SUFFIX_RE.sub("", periodical_name)
    publication = _PDF_ISSUE_PUBLICATION_RE.match(periodical_name)
    if publication is not None:
        periodical_name = publication.group("issue") + publication.group("suffix")

    special_keyword = next(
        (keyword for keyword in _PDF_SPECIAL_KEYWORDS if keyword in periodical_name),
        None,
    )
    numbered_prefix = (
        _PDF_EXPLICIT_VOLUME_PREFIX_RE.match(periodical_name)
        or _PDF_NUMBERED_ISSUE_PREFIX_RE.match(periodical_name)
    )
    has_special_issue_index = bool(
        numbered_prefix
        and int(numbered_prefix.group("issue")) <= _PDF_MAX_ISSUE
    )
    if special_keyword is not None and not has_special_issue_index:
        special_title = _clean_periodical_suffix(periodical_name)
        return f"{series_name} SP000 {special_title}.cbz"

    match = _PDF_PERIODICAL_RE.match(periodical_name)
    if match is None:
        return f"{stem}.cbz"

    first_issue = int(match.group(1))
    last_issue = int(match.group(2)) if match.group(2) else None
    suffix = match.group(3) or ""

    if first_issue > _PDF_MAX_ISSUE or (
        last_issue is not None and last_issue > _PDF_MAX_ISSUE
    ):
        return f"{stem}.cbz"

    if last_issue is not None:
        extra = _clean_periodical_suffix(suffix, "合刊")
        tail = f" 合刊{f' {extra}' if extra else ''}"
        return f"{series_name} v{first_issue:03d}-{last_issue:03d}{tail}.cbz"

    special_label = next((label for label in _PDF_SPECIAL_LABELS if label in suffix), None)
    if special_label is not None or special_keyword is not None:
        labels_to_remove = (special_label,) if special_label is not None else ()
        extra = _clean_periodical_suffix(suffix, *labels_to_remove)
        label = special_label or ""
        tail = " ".join(part for part in (label, extra) if part)
        tail = f" {tail}" if tail else ""
        return f"{series_name} SP{first_issue:03d}{tail}.cbz"

    extra = _clean_periodical_suffix(suffix)
    if extra in _PDF_MAIN_ISSUE_SUFFIXES:
        extra = ""
    tail = f" {extra}" if extra else ""
    return f"{series_name} v{first_issue:03d}{tail}.cbz"


def _rects_match(left, right, tolerance: float = 0.1) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _extract_full_page_jpeg(doc, page, output_path: str) -> bool:
    """Extract a page image only when doing so preserves the displayed page."""
    if page.rotation != 0 or page.first_annot is not None or page.first_widget is not None:
        return False

    images = page.get_image_info(xrefs=True)
    if len(images) != 1:
        return False

    info = images[0]
    xref = info.get("xref", 0)
    if xref <= 0 or info.get("has-mask", False):
        return False

    bbox = info.get("bbox")
    transform = info.get("transform")
    if bbox is None or transform is None or not _rects_match(bbox, page.rect):
        return False

    a, b, c, d, _, _ = transform
    if a <= 0 or d <= 0 or abs(b) > 0.1 or abs(c) > 0.1:
        return False

    display_items = page.get_bboxlog()
    if len(display_items) != 1:
        return False
    item_type, item_bbox = display_items[0]
    if item_type != "fill-image" or not _rects_match(item_bbox, page.rect):
        return False

    extracted = doc.extract_image(xref)
    if extracted.get("ext", "").lower() not in {"jpg", "jpeg"}:
        return False

    with open(output_path, "wb") as output_file:
        output_file.write(extracted["image"])
    return True


def _page_render_dpi(page, default_dpi: int) -> int:
    """Avoid upscaling a full-page scan when rendering overlays on top of it."""
    for info in page.get_image_info(xrefs=True):
        bbox = info.get("bbox")
        transform = info.get("transform")
        width = info.get("width", 0)
        height = info.get("height", 0)
        if bbox is None or transform is None or width <= 0 or height <= 0:
            continue
        if not _rects_match(bbox, page.rect):
            continue

        a, b, c, d, _, _ = transform
        if a <= 0 or d <= 0 or abs(b) > 0.1 or abs(c) > 0.1:
            continue

        dpi_x = width * 72.0 / max(page.rect.width, 1.0)
        dpi_y = height * 72.0 / max(page.rect.height, 1.0)
        effective_dpi = int(round(max(dpi_x, dpi_y)))
        if 36 <= effective_dpi <= default_dpi:
            return effective_dpi

    return default_dpi


def image_is_nearly_white(image: Image.Image) -> bool:
    """Detect MuPDF's silent all-white failure without rejecting normal white pages."""
    gray = image.convert("L").resize((64, 64), Image.Resampling.BILINEAR)
    try:
        low, high = gray.getextrema()
        pixels = list(gray.getdata())
        mean = sum(pixels) / len(pixels)
        return mean >= 250 and (high - low <= 5 or gray.entropy() < 0.25)
    finally:
        gray.close()


def _find_pdftoppm() -> str | None:
    if getattr(sys, "frozen", False):
        bundled = os.path.join(sys._MEIPASS, "poppler", "pdftoppm.exe")
        if os.path.isfile(bundled):
            return bundled
    configured = os.environ.get("PDFTOPPM_PATH")
    if configured and os.path.isfile(configured):
        return configured
    return shutil.which("pdftoppm") or shutil.which("pdftoppm.exe")


def _render_with_pdfium(pdfium_doc, page_index: int, dpi: int, output_path: str) -> bool:
    if pdfium_doc is None:
        return False
    page = bitmap = source_image = image = None
    try:
        page = pdfium_doc[page_index]
        bitmap = page.render(scale=dpi / 72.0)
        source_image = bitmap.to_pil()
        image = source_image.convert("RGB")
        image.save(output_path, "JPEG", quality=95)
        return not image_is_nearly_white(image)
    except Exception:
        return False
    finally:
        if image is not None:
            image.close()
        if source_image is not None:
            source_image.close()
        if bitmap is not None:
            bitmap.close()
        if page is not None:
            page.close()


def _render_with_poppler(
    pdftoppm: str | None,
    pdf_path: str,
    page_number: int,
    dpi: int,
    output_path: str,
) -> bool:
    if pdftoppm is None:
        return False

    output_base = os.path.splitext(output_path)[0] + "-poppler"
    generated_path = output_base + ".jpg"
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            [
                pdftoppm,
                "-f", str(page_number),
                "-l", str(page_number),
                "-singlefile",
                "-r", str(dpi),
                "-jpeg",
                "-jpegopt", "quality=95",
                pdf_path,
                output_base,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0 or not os.path.isfile(generated_path):
            return False
        os.replace(generated_path, output_path)
        return True
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        if os.path.isfile(generated_path):
            os.remove(generated_path)


def extract_or_render_with_pymupdf(
    pdf_path: str,
    temp_dir: str,
    dpi: int = 300,
) -> List[str]:
    """Extract full-page JPEGs directly and render all other pages one at a time."""
    if fitz is None:
        raise RuntimeError("PyMuPDF 未安装，请先安装 requirements.txt 中的依赖。")

    image_paths = []
    extracted_count = 0
    rendered_count = 0
    rendered_dpis = Counter()
    pdfium_count = 0
    poppler_count = 0
    pdfium_doc = None
    pdfium_open_attempted = False
    pdftoppm = _find_pdftoppm()
    with ExitStack() as resources:
        doc = resources.enter_context(fitz.open(pdf_path))
        for index, page in enumerate(doc, start=1):
            path = os.path.join(temp_dir, f"page-{index:04d}.jpg")
            if _extract_full_page_jpeg(doc, page, path):
                image_paths.append(path)
                extracted_count += 1
                continue

            render_dpi = _page_render_dpi(page, dpi)
            pix = page.get_pixmap(dpi=render_dpi, colorspace=fitz.csRGB, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            try:
                image.save(path, "JPEG", quality=95)
                suspicious_white = image_is_nearly_white(image)
            finally:
                image.close()
                pix = None

            if suspicious_white:
                if not pdfium_open_attempted:
                    pdfium_open_attempted = True
                    if pdfium is not None:
                        try:
                            pdfium_doc = pdfium.PdfDocument(pdf_path)
                            resources.callback(pdfium_doc.close)
                        except Exception:
                            pdfium_doc = None

                if _render_with_pdfium(pdfium_doc, index - 1, render_dpi, path):
                    pdfium_count += 1
                elif _render_with_poppler(pdftoppm, pdf_path, index, render_dpi, path):
                    poppler_count += 1
                else:
                    raise RuntimeError(
                        f"page {index} rendered nearly white in PyMuPDF and "
                        "could not be recovered by PDFium/Poppler"
                    )
            image_paths.append(path)
            rendered_count += 1
            rendered_dpis[render_dpi] += 1

    dpi_summary = ",".join(f"{value}dpi:{count}" for value, count in sorted(rendered_dpis.items()))
    print(
        f"  - PDF pages: extracted JPEG={extracted_count}, rendered={rendered_count}"
        f"{f' ({dpi_summary})' if dpi_summary else ''}"
        f"{f', recovered PDFium={pdfium_count}, Poppler={poppler_count}' if pdfium_count or poppler_count else ''}"
    )
    return image_paths
