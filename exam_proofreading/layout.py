"""Column detection utilities using OpenCV."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np

try:  # pragma: no cover - optional dependency
    import cv2
except Exception:  # pragma: no cover - optional dependency
    cv2 = None  # type: ignore

from PIL import Image

from .config import LayoutConfig

logger = logging.getLogger(__name__)


@dataclass
class ColumnBoundingBox:
    """Represents a detected column on the page."""

    x1: int
    y1: int
    x2: int
    y2: int

    def crop(self, image: Image.Image) -> Image.Image:
        return image.crop((self.x1, self.y1, self.x2, self.y2))


class ColumnDetector:
    """Detect multi-column layouts on page images."""

    def __init__(self, config: LayoutConfig):
        if cv2 is None:
            raise RuntimeError("opencv-python is required for column detection.")
        self.config = config

    def detect(self, image: Image.Image) -> List[ColumnBoundingBox]:
        logger.debug("Starting column detection")
        open_cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(open_cv_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        binary = 255 - binary  # invert: text becomes white
        projection = np.sum(binary / 255.0, axis=0)
        normalized = projection / np.max(projection)
        whitespace = normalized < (1 - self.config.whitespace_threshold)

        segments = self._find_segments(~whitespace)
        logger.debug("Detected %d potential column segments", len(segments))
        columns = self._merge_and_filter(segments, image.height)
        if not columns:
            columns = [ColumnBoundingBox(0, 0, image.width, image.height)]
        columns.sort(key=lambda box: box.x1)
        logger.debug("Returning %d column boxes", len(columns))
        return columns

    def _find_segments(self, mask: np.ndarray) -> List[Tuple[int, int]]:
        segments: List[Tuple[int, int]] = []
        start = None
        for idx, value in enumerate(mask):
            if value and start is None:
                start = idx
            elif not value and start is not None:
                segments.append((start, idx))
                start = None
        if start is not None:
            segments.append((start, len(mask)))
        return segments

    def _merge_and_filter(self, segments: Sequence[Tuple[int, int]], height: int) -> List[ColumnBoundingBox]:
        min_width = self.config.minimum_column_width
        boxes: List[ColumnBoundingBox] = []
        for x1, x2 in segments:
            if x2 - x1 < min_width:
                continue
            boxes.append(ColumnBoundingBox(x1=x1, y1=0, x2=x2, y2=height))
        if len(boxes) > self.config.maximum_columns:
            boxes = sorted(boxes, key=lambda box: box.x2 - box.x1, reverse=True)[: self.config.maximum_columns]
        return boxes


__all__ = ["ColumnBoundingBox", "ColumnDetector"]
