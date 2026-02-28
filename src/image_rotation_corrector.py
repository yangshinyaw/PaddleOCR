"""
Content-Aware Rotation Corrector for Receipt Images
=====================================================
Detects and corrects 90° / 180° / 270° gross rotations.

WHY THE OLD PASS 2 (confidence comparison) FAILED
--------------------------------------------------
PaddleOCR with use_angle_cls=True auto-corrects each individual text LINE
before recognizing it. So OCR confidence is nearly identical at 0° and 180°
— the engine reads every line correctly regardless of the image being upside-down.
The only difference is the ORDER of lines (bottom lines come out first when inverted).

NEW APPROACH: TWO PASSES
-------------------------

Pass 1 — Aspect ratio  (<1ms)
  Receipts are always portrait. If image is landscape (w > h * 1.1),
  it is rotated 90°. We run OCR at 90° CW and 90° CCW and pick whichever
  gives more detected lines.

Pass 2 — Spatial keyword analysis  (~same cost as one OCR run)
  Run OCR ONCE on the portrait image with return_positions=True.
  Get bounding box Y coordinates for each detected text line.

  On a CORRECT receipt:
    - Store name / header keywords → TOP third (small Y values)
    - Footer keywords (THIS IS YOUR INVOICE, TXN#, etc.) → BOTTOM third

  On an UPSIDE-DOWN (180°) receipt:
    - Footer keywords appear at TOP (small Y)
    - Store name appears at BOTTOM
  → Rotate 180°.

  PaddleOCR bbox Y coords always reflect physical image position even when
  use_angle_cls=True corrects the reading direction per-line.

Pass 3 — Post-OCR text-line order check  (<1ms)
  Called AFTER main OCR from receipt_processor.py.
  Safety net: checks if footer keywords appear in the first 30% of text_lines.
"""

import cv2
import numpy as np
import tempfile
import os
from typing import Tuple, Optional, List
from pathlib import Path

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ── Keyword lists ──────────────────────────────────────────────────────────────

# These belong at the TOP of a correctly-oriented receipt
_HEADER_KEYWORDS = [
    "MERCURY DRUG",
    "SM SUPERMARKET", "SM HYPERMARKET",
    "JOLLIBEE", "MCDONALD",
    "7-ELEVEN", "MINISTOP",
    "WATSONS", "ROSE PHARMACY", "GENERIKA", "SOUTH STAR",
    "ROBINSONS", "PUREGOLD", "SAVEMORE", "LANDMARK", "MANSON",
]

# These belong at the BOTTOM of a correctly-oriented receipt
_FOOTER_KEYWORDS = [
    "THIS IS YOUR INVOICE",
    "- THIS IS YOUR INVOICE -",
    "TXN#",
    "INVOICE#",
    "PTU NO",
    "PTU No.",
    "ACCRED NO",
    "PHILLOGIX",
    "MARAMING SALAMAT",
    "SALAMAT PO",
    "THANK YOU FOR",
]

_ROTATION_MAP = {
    90:  cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def _rotate(img: np.ndarray, degrees: int) -> np.ndarray:
    if degrees == 0:
        return img
    return cv2.rotate(img, _ROTATION_MAP[degrees])


def _bbox_center_y(bbox) -> float:
    """Get center Y from PaddleOCR bbox [[x,y],[x,y],[x,y],[x,y]]."""
    y_coords = [pt[1] for pt in bbox]
    return (min(y_coords) + max(y_coords)) / 2.0


class ImageRotationCorrector:
    """
    Detects and corrects gross rotation in receipt photos.
    Instantiated once in ReceiptProcessor.__init__ with the live OCR engine.
    """

    def __init__(self, ocr_engine=None):
        self._ocr = ocr_engine
        logger.info("ImageRotationCorrector initialized (spatial bbox mode)")

    # ── Public API ─────────────────────────────────────────────────────────────

    def detect_and_correct(
        self, image_path: str, output_path: Optional[str] = None
    ) -> Tuple[str, int]:
        """
        Detect rotation and save corrected image if needed.

        Returns:
            (path, degrees_corrected)  — degrees=0 means no change needed.
        """
        img = cv2.imread(image_path)
        if img is None:
            logger.warning(f"[Rotation] Cannot read image: {image_path}")
            return image_path, 0

        rotation = self._detect(img)

        if rotation == 0:
            logger.info("[Rotation] No rotation correction needed")
            return image_path, 0

        corrected = _rotate(img, rotation)

        if output_path is None:
            stem   = Path(image_path).stem
            suffix = Path(image_path).suffix
            output_path = str(
                Path(image_path).parent / f"rot{rotation}_{stem}{suffix}"
            )

        cv2.imwrite(output_path, corrected)
        logger.info(f"[Rotation] Applied {rotation}° correction → {output_path}")
        return output_path, rotation

    def check_text_orientation(self, text_lines: List[str]) -> int:
        """
        Pass 3: cheap post-OCR sanity check on text line ORDER.
        Called from receipt_processor.py after main OCR completes.

        Returns 180 if upside-down detected, else 0.
        """
        if not text_lines or len(text_lines) < 4:
            return 0

        n   = len(text_lines)
        top = " ".join(text_lines[: n // 3]).upper()
        bot = " ".join(text_lines[n * 2 // 3 :]).upper()

        footer_at_top  = sum(1 for kw in _FOOTER_KEYWORDS if kw.upper() in top)
        header_at_top  = sum(1 for kw in _HEADER_KEYWORDS if kw.upper() in top)
        header_at_bot  = sum(1 for kw in _HEADER_KEYWORDS if kw.upper() in bot)

        logger.info(
            f"[Rotation] Pass3 text check: "
            f"footer_at_top={footer_at_top} header_at_top={header_at_top} "
            f"header_at_bot={header_at_bot}"
        )

        if footer_at_top >= 1 and header_at_top == 0:
            return 180
        if header_at_bot >= 1 and header_at_top == 0:
            return 180
        return 0

    # ── Internal ───────────────────────────────────────────────────────────────

    def _detect(self, img: np.ndarray) -> int:
        """Run passes in order. Returns degrees to rotate to fix orientation."""
        h, w = img.shape[:2]

        # Pass 1: landscape = 90° off
        if w > h * 1.1:
            logger.info(
                f"[Rotation] Pass1: landscape {w}x{h}, "
                f"picking CW vs CCW via line count"
            )
            return self._pick_landscape_rotation(img)

        # Pass 2: spatial analysis for upside-down portrait images
        if self._ocr is not None:
            return self._pass2_spatial(img)

        return 0

    def _pick_landscape_rotation(self, img: np.ndarray) -> int:
        """
        Image is landscape => rotated either 90 CW or 90 CCW.

        WHY NOT LINE COUNT: use_angle_cls=True means PaddleOCR auto-corrects
        per-line angle, so line counts are equal for both candidates.

        CORRECT APPROACH: use the same spatial keyword analysis as Pass 2.
        Run OCR on both candidates, check which has header keywords at top.
        Defaults to 270 (CCW) which is the most common phone orientation.
        """
        if self._ocr is None:
            return 270  # CCW is most common phone orientation for receipts

        h, w = img.shape[:2]
        scale = min(1.0, 1200 / max(h, w))
        small = cv2.resize(img, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_AREA)

        ocr_results = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            for deg in (90, 270):
                candidate = _rotate(small, deg)
                tmp = os.path.join(tmpdir, f"r{deg}.jpg")
                cv2.imwrite(tmp, candidate)
                try:
                    ocr_results[deg] = self._ocr.extract_text(
                        tmp, return_confidence=True, return_positions=True
                    )
                    logger.info(
                        f"[Rotation] landscape {deg}: "
                        f"{len(ocr_results[deg].get('lines', []))} lines"
                    )
                except Exception as e:
                    logger.debug(f"[Rotation] OCR at {deg} failed: {e}")
                    ocr_results[deg] = {"lines": []}

        # After 90-degree rotation, the new height equals the old width
        candidate_h = int(w * scale)

        for deg in (90, 270):
            lines = ocr_results.get(deg, {}).get("lines", [])
            if not lines:
                continue

            top_thresh = candidate_h * 0.35

            header_in_top = 0
            footer_in_top = 0

            for line in lines:
                text = line.get("text", "").upper()
                bbox = line.get("bbox")
                if not bbox:
                    continue
                cy = _bbox_center_y(bbox)

                for kw in _HEADER_KEYWORDS:
                    if kw.upper() in text and cy < top_thresh:
                        header_in_top += 1
                        logger.debug(f"[Rotation] {deg}: header '{kw}' Y={cy:.0f}")

                for kw in _FOOTER_KEYWORDS:
                    if kw.upper() in text and cy < top_thresh:
                        footer_in_top += 1
                        logger.debug(f"[Rotation] {deg}: footer '{kw}' Y={cy:.0f}")

            logger.info(
                f"[Rotation] {deg}: header_in_top={header_in_top} "
                f"footer_in_top={footer_in_top}"
            )

            # Correct orientation: header at top, no footer at top
            if header_in_top >= 1 and footer_in_top == 0:
                logger.info(f"[Rotation] landscape winner: {deg}")
                return deg

        logger.info("[Rotation] landscape: no clear winner, defaulting to 270")
        return 270

    def _pass2_spatial(self, img: np.ndarray) -> int:
        """
        Run OCR once on a downsampled portrait image.
        Check if footer keywords land in the top portion (= upside-down).
        Returns 0 or 180.
        """
        h, w = img.shape[:2]
        scale = min(1.0, 1200 / max(h, w))
        if scale < 1.0:
            small  = cv2.resize(img, None, fx=scale, fy=scale,
                                interpolation=cv2.INTER_AREA)
            img_h  = int(h * scale)
        else:
            small  = img
            img_h  = h

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = os.path.join(tmpdir, "spatial_check.jpg")
            cv2.imwrite(tmp, small)
            try:
                result = self._ocr.extract_text(
                    tmp, return_confidence=True, return_positions=True
                )
            except Exception as e:
                logger.debug(f"[Rotation] Pass2 OCR failed: {e}")
                return 0

        lines = result.get("lines", [])
        if not lines:
            return 0

        top_thresh    = img_h * 0.35   # top 35% of image
        bottom_thresh = img_h * 0.65   # bottom 35% of image

        footer_in_top    = 0
        header_in_top    = 0
        header_in_bottom = 0

        for line in lines:
            text = line.get("text", "").upper()
            bbox = line.get("bbox")
            if not bbox:
                continue
            cy = _bbox_center_y(bbox)

            for kw in _FOOTER_KEYWORDS:
                if kw.upper() in text:
                    if cy < top_thresh:
                        footer_in_top += 1
                        logger.debug(
                            f"[Rotation] Footer '{kw}' at Y={cy:.0f} "
                            f"(top={top_thresh:.0f}) → inversion signal"
                        )

            for kw in _HEADER_KEYWORDS:
                if kw.upper() in text:
                    if cy < top_thresh:
                        header_in_top += 1
                    if cy > bottom_thresh:
                        header_in_bottom += 1
                        logger.debug(
                            f"[Rotation] Header '{kw}' at Y={cy:.0f} "
                            f"(bottom={bottom_thresh:.0f}) → inversion signal"
                        )

        logger.info(
            f"[Rotation] Pass2 spatial: img_h={img_h} "
            f"footer_in_top={footer_in_top} "
            f"header_in_top={header_in_top} "
            f"header_in_bottom={header_in_bottom}"
        )

        # Footer at top AND no header at top = upside-down
        if footer_in_top >= 1 and header_in_top == 0:
            return 180
        # Header at bottom AND nothing at top = upside-down
        if header_in_bottom >= 1 and header_in_top == 0:
            return 180

        return 0