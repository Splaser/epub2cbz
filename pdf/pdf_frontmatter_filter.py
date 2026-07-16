import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from PIL import Image


_OCR_ENGINE = None
_OCR_INIT_ATTEMPTED = False
_DISCLAIMER_FINGERPRINTS = []
_MAX_FINGERPRINTS = 32
_DISCLAIMER_TITLES = ("免责声明", "免責聲明", "免责申明", "免責申明")
_DISCLAIMER_CATEGORIES = {
    "copyright": ("版权归", "版權歸", "作者所有", "出版社及作者"),
    "noncommercial": ("非盈利", "非赢利", "非營利", "商业盈利", "商業盈利", "商业目的", "商業目的"),
    "download": ("下载资源", "下載資源", "下载后24小时", "下載後24小時", "24小时内删除", "24小時內刪除"),
    "liability": ("法律责任", "法律責任", "后果自负", "後果自負", "不承担", "不承擔"),
    "learning": ("交流学习", "交流學習", "学习之用", "學習之用", "阅读学习", "閱讀學習"),
    "piracy": ("盗版", "盜版", "购买正版", "購買正版", "请购买正版", "請購買正版"),
    "infringement": ("权利造成了侵犯", "權利造成了侵犯", "侵权", "侵權", "撤销相关内容", "撤銷相關內容"),
}


@dataclass(frozen=True)
class DisclaimerDetection:
    is_disclaimer: bool
    score: int
    hits: tuple[str, ...]


@dataclass(frozen=True)
class _PageFingerprint:
    aspect_milli: int
    difference_hash: int
    average_hash: int


def _get_ocr_engine():
    global _OCR_ENGINE, _OCR_INIT_ATTEMPTED
    if _OCR_INIT_ATTEMPTED:
        return _OCR_ENGINE

    _OCR_INIT_ATTEMPTED = True
    try:
        # Keep RapidOCR optional and lazy. A broken PyInstaller data bundle must
        # not prevent the PDF converter from starting or converting pages.
        from rapidocr import RapidOCR

        _OCR_ENGINE = RapidOCR()
    except Exception as exc:
        print(
            "WARNING: PDF front-page OCR is unavailable; "
            f"disclaimer pages will be kept ({exc})"
        )
    return _OCR_ENGINE


def _normalize_ocr_text(lines: Iterable[str]) -> str:
    text = "".join(str(line) for line in lines if line)
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE).casefold()


def _image_fingerprint(image_path: str) -> Optional[_PageFingerprint]:
    try:
        with Image.open(image_path) as image:
            gray = image.convert("L")
            aspect_milli = round(image.width * 1000 / max(image.height, 1))

            difference = gray.resize((17, 16), Image.Resampling.LANCZOS)
            pixels = list(difference.getdata())
            difference_hash = 0
            for row in range(16):
                offset = row * 17
                for column in range(16):
                    difference_hash <<= 1
                    difference_hash |= pixels[offset + column] > pixels[offset + column + 1]

            averaged = gray.resize((16, 16), Image.Resampling.LANCZOS)
            average_pixels = list(averaged.getdata())
            average = sum(average_pixels) / len(average_pixels)
            average_hash = 0
            for value in average_pixels:
                average_hash <<= 1
                average_hash |= value >= average

        return _PageFingerprint(aspect_milli, difference_hash, average_hash)
    except Exception:
        return None


def _fingerprint_match(fingerprint: Optional[_PageFingerprint]) -> Optional[tuple[int, int]]:
    if fingerprint is None:
        return None

    best_match = None
    for known in _DISCLAIMER_FINGERPRINTS:
        if abs(fingerprint.aspect_milli - known.aspect_milli) > 8:
            continue
        difference_distance = (fingerprint.difference_hash ^ known.difference_hash).bit_count()
        average_distance = (fingerprint.average_hash ^ known.average_hash).bit_count()
        if difference_distance <= 16 and average_distance <= 20:
            distance = (difference_distance, average_distance)
            if best_match is None or distance < best_match:
                best_match = distance
    return best_match


def _remember_disclaimer_fingerprint(fingerprint: Optional[_PageFingerprint]) -> None:
    if fingerprint is None or len(_DISCLAIMER_FINGERPRINTS) >= _MAX_FINGERPRINTS:
        return
    if _fingerprint_match(fingerprint) is None:
        _DISCLAIMER_FINGERPRINTS.append(fingerprint)


def detect_disclaimer_page(image_path: str) -> DisclaimerDetection:
    engine = _get_ocr_engine()
    if engine is None:
        return DisclaimerDetection(False, 0, ("ocr-unavailable",))

    try:
        result = engine(image_path)
        lines = getattr(result, "txts", None) or ()
        scores = getattr(result, "scores", None) or ()
        if scores and len(scores) == len(lines):
            lines = [line for line, confidence in zip(lines, scores) if confidence >= 0.55]
        text = _normalize_ocr_text(lines)
    except Exception as exc:
        return DisclaimerDetection(False, 0, (f"ocr-error:{exc}",))

    title_hit = next((phrase for phrase in _DISCLAIMER_TITLES if phrase.casefold() in text), None)
    category_hits = []
    for category, phrases in _DISCLAIMER_CATEGORIES.items():
        if any(phrase.casefold() in text for phrase in phrases):
            category_hits.append(category)

    score = (4 if title_hit else 0) + len(category_hits)
    is_disclaimer = (title_hit is not None and len(category_hits) >= 1) or len(category_hits) >= 4
    hits = ([f"title:{title_hit}"] if title_hit else []) + category_hits
    return DisclaimerDetection(is_disclaimer, score, tuple(hits))


def filter_leading_disclaimer_pages(
    image_paths: List[str],
    *,
    max_pages: int = 3,
) -> List[str]:
    """Remove only consecutive disclaimer pages at the very start of a PDF."""
    remove_count = 0
    template_only_prefix = True
    for image_path in image_paths[:max_pages]:
        fingerprint = _image_fingerprint(image_path)
        template_distance = _fingerprint_match(fingerprint)
        if template_distance is not None:
            detection = DisclaimerDetection(
                True,
                0,
                (f"template:dhash={template_distance[0]}/ahash={template_distance[1]}",),
            )
        else:
            # A known disclaimer prefix was followed by an unknown page. Keep it
            # and stop immediately instead of running OCR on every issue cover.
            if remove_count > 0 and template_only_prefix:
                break
            template_only_prefix = False
            detection = detect_disclaimer_page(image_path)
            if detection.is_disclaimer:
                _remember_disclaimer_fingerprint(fingerprint)
        if not detection.is_disclaimer:
            break

        print(
            "  - skip [pdf-front-disclaimer:"
            f"score={detection.score} hits={','.join(detection.hits)}] "
            f"{os.path.basename(image_path)}"
        )
        remove_count += 1

    return image_paths[remove_count:]
