"""Text backend: OCR over rasterized pages, via Tesseract.

The fallback channel. It exists for documents the text layer cannot serve --
scanned older publications, image-only supplementary PDFs -- and it is only
asked for the pages that need it, because it is both slower and lossier than
reading the embedded text.

Tool choice: Tesseract first because it installs in one command and is adequate
on clean printed text. The blueprint names PaddleOCR (section 28), which is more
accurate but whose wheels are a known time sink on Apple Silicon; if accuracy
proves insufficient the step up is ``rapidocr-onnxruntime`` (the same PP-OCR
models on ONNX runtime) rather than building Paddle.

Unlike the text layer, this channel is approximate, so every page it produces
carries a real ``confidence`` and downstream consumers are expected to weigh it.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

from reprolens.documents.base import Backend, PageText
from reprolens.documents.textrepair import rejoin_broken_urls

# 300 DPI is the usual floor for reliable OCR of small print such as the
# footnote-sized type that data-availability statements are often set in.
DEFAULT_DPI = 300

# Tesseract reports -1 for non-text regions; those are not failed words.
_NO_CONFIDENCE = -1


class OcrBackend:
    name: Backend = "ocr"

    def __init__(self, dpi: int = DEFAULT_DPI, language: str = "eng") -> None:
        self.dpi = dpi
        self.language = language

    def read(self, path: Path, pages: list[int] | None = None) -> list[PageText]:
        """OCR the whole document, or only ``pages`` (1-indexed) when given."""
        out: list[PageText] = []
        with pymupdf.open(path) as doc:
            for index, page in enumerate(doc, start=1):
                if pages is not None and index not in pages:
                    continue
                text, confidence = self._read_page(page)
                out.append(
                    PageText(
                        page=index,
                        text=text,
                        links=[],  # a rasterized page has no annotations
                        has_images=True,
                        backend=self.name,
                        confidence=confidence,
                    )
                )
        return out

    def _read_page(self, page: pymupdf.Page) -> tuple[str, float | None]:
        image = _rasterize(page, self.dpi)
        data = pytesseract.image_to_data(
            image, lang=self.language, output_type=pytesseract.Output.DICT
        )
        return _reflow(data), _mean_confidence(data)


def _rasterize(page: pymupdf.Page, dpi: int) -> Image.Image:
    pixmap = page.get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pixmap.tobytes("png")))


def _reflow(data: dict) -> str:
    """Rebuild lines from Tesseract's word boxes.

    Word order alone is not enough: identifiers must not be split across what
    were separate lines, and a line break inside an accession is exactly the
    failure this project cannot tolerate. Grouping by Tesseract's own
    block/paragraph/line indices keeps the layout it detected.
    """
    lines: dict[tuple[int, int, int, int], list[str]] = {}
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        key = (data["page_num"][i], data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)

    # Same URL repair as the text-layer channel. Tesseract splits
    # "https://doi.org/10." from "1038/s41587-023-01767-y", which otherwise
    # costs a real identifier.
    rendered = [" ".join(words) for _key, words in sorted(lines.items())]
    return rejoin_broken_urls(rendered)


def _mean_confidence(data: dict) -> float | None:
    scores = [
        float(c)
        for c, word in zip(data["conf"], data["text"], strict=True)
        if word.strip() and float(c) != _NO_CONFIDENCE
    ]
    return sum(scores) / len(scores) / 100.0 if scores else None
