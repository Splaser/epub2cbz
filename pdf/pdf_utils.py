import os
import re
from collections import Counter
from typing import List

from PIL import Image

try:
    import fitz
except ImportError:
    fitz = None


def clean_pdf_name(name: str) -> str:
    name = re.sub(r'\s+\d+x\d+(?:\.\d+)?\+\d+x\d+(?:\.\d+)?=\d+(?:\.\d+)?', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


_PDF_PERIODICAL_RE = re.compile(
    r"^(?:(?:vol(?:ume)?\.?|v)\s*)?0*(\d{1,3})(?!\d)"
    r"(?:\s*[~～\-–—]\s*(?:vol(?:ume)?\.?|v)?\s*0*(\d{1,3})(?!\d))?"
    r"(.*)$",
    flags=re.IGNORECASE,
)
_PDF_EMBEDDED_VOLUME_RE = re.compile(
    r"\bvol(?:ume)?\.?\s*0*(?P<issue>\d{1,3})(?!\d)(?P<suffix>.*)$",
    flags=re.IGNORECASE,
)
_PDF_ISSUE_PUBLICATION_RE = re.compile(
    r"^(?P<issue>\d{3}(?:\s*[~～\-–—]\s*\d{3})?)"
    r"\s+\(?(?:19|20)\d{2}\.(?:0?[1-9]|1[0-2])(?:AB|A|B)?\)?"
    r"(?P<suffix>.*)$",
    flags=re.IGNORECASE,
)
_PDF_RELEASE_GROUP_PREFIX_RE = re.compile(
    r"^[\s_.-]*(?:full[\s_.-]*)?CRAZ(?=$|[\s_.-])",
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
    r"^(?:vol(?:ume)?\.?|v)\s*0*\d{1,3}(?!\d)",
    flags=re.IGNORECASE,
)
_PDF_THREE_DIGIT_ISSUE_PREFIX_RE = re.compile(r"^\d{3}(?!\d)")


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
        periodical_name = embedded_volume.group("issue") + embedded_volume.group("suffix")

    publication = _PDF_ISSUE_PUBLICATION_RE.match(periodical_name)
    if publication is not None:
        suffix = _PDF_RELEASE_GROUP_PREFIX_RE.sub("", publication.group("suffix"))
        periodical_name = publication.group("issue") + suffix

    special_keyword = next(
        (keyword for keyword in _PDF_SPECIAL_KEYWORDS if keyword in periodical_name),
        None,
    )
    has_special_issue_index = bool(
        _PDF_EXPLICIT_VOLUME_PREFIX_RE.match(periodical_name)
        or _PDF_THREE_DIGIT_ISSUE_PREFIX_RE.match(periodical_name)
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
    with fitz.open(pdf_path) as doc:
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
            finally:
                image.close()
                pix = None
            image_paths.append(path)
            rendered_count += 1
            rendered_dpis[render_dpi] += 1

    dpi_summary = ",".join(f"{value}dpi:{count}" for value, count in sorted(rendered_dpis.items()))
    print(
        f"  - PDF pages: extracted JPEG={extracted_count}, rendered={rendered_count}"
        f"{f' ({dpi_summary})' if dpi_summary else ''}"
    )
    return image_paths
