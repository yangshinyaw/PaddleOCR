"""
Smart Adaptive Preprocessor for Receipt OCR
Version 3.0 - Properly targeted preprocessing

PHILOSOPHY:
  PaddleOCR PP-OCRv3 has strong built-in preprocessing:
    - Internal grayscale conversion
    - Contrast normalization
    - Edge enhancement
    - Its own sharpening

  Our job is ONLY to fix things PaddleOCR cannot fix itself:
    1. Severe darkness / underexposure  → gamma correction
    2. Shadows / uneven lighting        → background normalization
    3. Very low contrast (thermal fade) → gentle CLAHE only
    4. Slight rotation / skew           → deskew
    5. Extreme resolution               → resize to safe range

  What we NEVER do:
    - Aggressive sharpening (double-sharpens with PaddleOCR internals)
    - Adaptive thresholding (destroys gradient info PaddleOCR needs)
    - CLAHE on already-good images (makes them worse)
    - Convert to grayscale (PaddleOCR prefers color — better det model)

PIPELINE:
  analyze_image() → returns ImageProfile with detected conditions
  preprocess()    → applies ONLY fixes needed for detected conditions
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path

import cv2
import numpy as np

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ─── Image profile ────────────────────────────────────────────────────────────

@dataclass
class ImageProfile:
    """Measured properties of the input image."""
    mean_brightness: float = 0.0
    std_contrast: float = 0.0
    shadow_variance: float = 0.0   # variance of local brightness patches
    skew_angle: float = 0.0        # degrees, positive = clockwise
    width: int = 0
    height: int = 0

    # Derived condition flags (set by analyze_image)
    is_dark: bool = False           # mean < 80
    is_very_dark: bool = False      # mean < 50
    is_low_contrast: bool = False   # std < 35
    has_shadow: bool = False        # high local brightness variance
    needs_deskew: bool = False      # |angle| > 1.5°
    is_too_large: bool = False      # max dim > 4096
    is_too_small: bool = False      # max dim < 600
    is_small_text: bool = False          # estimated text height < 20px at current resolution
    estimated_text_height_px: float = 0.0
    is_noisy: bool = False               # high-ISO digital noise detected
    is_overexposed: bool = False         # blown-out highlights (mean > 200)
    has_perspective: bool = False        # trapezoid / keystone distortion detected
    noise_level: float = 0.0            # measured noise sigma
    perspective_pts: object = None       # 4 corner points for perspective fix

    applied: List[str] = field(default_factory=list)  # log of what was done


# ─── Main class ───────────────────────────────────────────────────────────────

class ImagePreprocessor:
    """
    Smart receipt image preprocessor.

    Analyzes each image and applies only the targeted corrections needed.
    Designed to complement PaddleOCR's built-in preprocessing, not duplicate it.
    """

    # Thresholds
    DARK_MEAN       = 80    # below → dark image, apply gamma
    VERY_DARK_MEAN  = 50    # below → very dark, stronger gamma
    LOW_CONTRAST    = 35    # std_dev below → apply gentle CLAHE
    SHADOW_VAR      = 900   # local brightness variance above → shadow present
    SKEW_MIN        = 1.5   # degrees, below → skip deskew
    SMALL_TEXT_PX     = 20    # estimated text height below this → upscale before OCR
    SMALL_TEXT_TARGET = 2400  # upscale small-text images so longest side = this
    NOISE_THRESHOLD   = 8.0   # noise sigma above this → denoise
    OVEREXPOSE_MEAN   = 200   # mean brightness above this → overexposed
    OVEREXPOSE_HIGH   = 230   # very overexposed
    MAX_SIDE        = 4096  # pixels, above → resize down
    TARGET_SIDE     = 2560  # target max side when resizing
    MIN_SIDE        = 600   # below → upscale slightly

    def __init__(self, config_path: Optional[str] = None):
        logger.info("ImagePreprocessor v3 initialized (smart adaptive mode)")

    # ── Public API ────────────────────────────────────────────────────────────

    def preprocess(self, image_path: str, output_path: Optional[str] = None) -> str:
        """
        Main entry point. Analyzes then applies only needed corrections.

        Args:
            image_path:  Path to input receipt image
            output_path: Optional output path (auto-generated if None)

        Returns:
            Path to preprocessed image (or original if no processing needed)
        """
        img_bgr = cv2.imread(image_path)
        if img_bgr is None:
            raise ValueError(f"Cannot read image: {image_path}")

        profile = self._analyze(img_bgr)

        logger.info(
            f"[Preprocessor] mean={profile.mean_brightness:.0f} "
            f"std={profile.std_contrast:.0f} "
            f"shadow_var={profile.shadow_variance:.0f} "
            f"skew={profile.skew_angle:.1f}°  "
            f"size={profile.width}x{profile.height}"
        )
        logger.info(
            f"[Preprocessor] flags: dark={profile.is_dark} "
            f"low_contrast={profile.is_low_contrast} "
            f"shadow={profile.has_shadow} "
            f"deskew={profile.needs_deskew}"
        )

        # Apply targeted corrections
        img_bgr = self._apply(img_bgr, profile)

        if not profile.applied:
            # Nothing was needed — return original to avoid unnecessary I/O
            logger.info("[Preprocessor] Image quality OK — no preprocessing needed")
            return image_path

        # Save result
        if output_path is None:
            output_dir = Path(image_path).parent.parent / "data" / "temp"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"pre_{Path(image_path).name}")

        cv2.imwrite(output_path, img_bgr)
        logger.info(f"[Preprocessor] Applied: {', '.join(profile.applied)} → {output_path}")
        return output_path

    def analyze_image_quality(self, image_path: str) -> dict:
        """Utility: return quality metrics as a plain dict (for API/debugging)."""
        img = cv2.imread(image_path)
        if img is None:
            return {"error": "Cannot read image"}
        p = self._analyze(img)
        return {
            "mean_brightness": round(p.mean_brightness, 1),
            "std_contrast":    round(p.std_contrast, 1),
            "shadow_variance": round(p.shadow_variance, 1),
            "skew_angle":      round(p.skew_angle, 2),
            "width": p.width, "height": p.height,
            "is_dark":               p.is_dark,
            "is_very_dark":          p.is_very_dark,
            "is_low_contrast":       p.is_low_contrast,
            "has_shadow":            p.has_shadow,
            "needs_deskew":          p.needs_deskew,
            "is_small_text":            p.is_small_text,
            "estimated_text_height_px": round(p.estimated_text_height_px, 1),
            "is_noisy":                 p.is_noisy,
            "noise_level":              round(p.noise_level, 2),
            "is_overexposed":           p.is_overexposed,
            "has_perspective":          p.has_perspective,
            "recommended_fixes": self._recommend(p),
        }

    # Kept for backward compat with any callers
    def preprocess_minimal(self, image_path: str, output_path: Optional[str] = None) -> str:
        """Grayscale only — kept for backward compatibility."""
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        op = output_path or str(
            Path(image_path).parent / f"gray_{Path(image_path).name}"
        )
        cv2.imwrite(op, gray)
        return op

    def preprocess_adaptive(self, image_path: str, output_path: Optional[str] = None) -> str:
        """Routes to the new smart preprocess() — kept for backward compatibility."""
        return self.preprocess(image_path, output_path)

    def preprocess_with_shadow_removal(self, image_path: str, output_path: Optional[str] = None) -> str:
        """Shadow removal only — kept for backward compatibility."""
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Cannot read: {image_path}")
        result = self._remove_shadow(img)
        op = output_path or str(
            Path(image_path).parent / f"noshadow_{Path(image_path).name}"
        )
        cv2.imwrite(op, result)
        return op

    # ── Analysis ──────────────────────────────────────────────────────────────

    def _analyze(self, img_bgr: np.ndarray) -> ImageProfile:
        """Measure image properties and set condition flags."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        mean = float(np.mean(gray))
        std  = float(np.std(gray))

        # Shadow = high variance between local brightness regions
        # Divide into 4x4 grid, measure mean of each cell
        rows, cols = 4, 4
        cell_means = []
        for r in range(rows):
            for c in range(cols):
                y1, y2 = r * h // rows, (r + 1) * h // rows
                x1, x2 = c * w // cols, (c + 1) * w // cols
                cell_means.append(float(np.mean(gray[y1:y2, x1:x2])))
        shadow_var = float(np.var(cell_means))

        # Skew angle via Hough lines on edges
        skew = self._estimate_skew(gray)

        p = ImageProfile(
            mean_brightness=mean,
            std_contrast=std,
            shadow_variance=shadow_var,
            skew_angle=skew,
            width=w, height=h,
        )

        p.is_very_dark    = mean < self.VERY_DARK_MEAN
        p.is_dark         = mean < self.DARK_MEAN
        p.is_low_contrast = std < self.LOW_CONTRAST
        p.has_shadow      = shadow_var > self.SHADOW_VAR and not p.is_dark
        p.needs_deskew    = abs(skew) > self.SKEW_MIN
        p.is_too_large    = max(w, h) > self.MAX_SIDE
        p.is_too_small    = max(w, h) < self.MIN_SIDE

        # Estimate text height in pixels
        # Receipts typically have ~40-60 lines of text
        # Each line occupies roughly 1/50 of the image height
        # Text characters are about 70% of line height
        estimated_line_h = h / 50.0
        p.estimated_text_height_px = estimated_line_h * 0.70
        p.is_small_text = (
            p.estimated_text_height_px < self.SMALL_TEXT_PX
            and not p.is_too_large
        )

        # Noise detection
        # Measure noise in a uniform background area (top 10% of image,
        # which is usually blank receipt header space).
        # We use the median absolute deviation of local variance patches.
        p.noise_level, p.is_noisy = self._measure_noise(gray, h, w)

        # Overexposure detection
        p.is_overexposed = mean > self.OVEREXPOSE_MEAN

        # Perspective distortion detection
        p.has_perspective, p.perspective_pts = self._detect_perspective(img_bgr)

        return p

    def _estimate_skew(self, gray: np.ndarray) -> float:
        """
        Estimate rotation angle using Hough line transform.
        Returns angle in degrees. 0 = straight. Positive = clockwise tilt.
        Fast and conservative — only fires if clearly tilted.
        """
        try:
            # Edge detection on downscaled image for speed
            scale = min(1.0, 800 / max(gray.shape))
            small = cv2.resize(gray, None, fx=scale, fy=scale)
            edges = cv2.Canny(small, 50, 150, apertureSize=3)
            lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)
            if lines is None or len(lines) < 5:
                return 0.0
            angles = []
            for line in lines[:50]:
                theta = line[0][1]
                # Convert to degrees from vertical
                angle = np.degrees(theta) - 90
                # Only consider near-horizontal lines
                if abs(angle) < 45:
                    angles.append(angle)
            if not angles:
                return 0.0
            # Use median to be robust against outliers
            return float(np.median(angles))
        except Exception:
            return 0.0

    # ── Apply targeted fixes ──────────────────────────────────────────────────

    def _apply(self, img: np.ndarray, p: ImageProfile) -> np.ndarray:
        """Apply only the corrections flagged by the profile."""

        # 0. Perspective correction FIRST — straighten trapezoid before all else.
        #    Must come before deskew and brightness fixes because those assume
        #    a rectangular document. A warped image will fool the skew estimator.
        if p.has_perspective and p.perspective_pts is not None:
            img = self._correct_perspective(img, p.perspective_pts)
            p.applied.append("perspective_correction")
            # Re-analyze after correction (dimensions may have changed)
            gray_new = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            p.height, p.width = gray_new.shape[:2]

        # 1. Upscale for small text FIRST — before any other processing
        #    Small text (< 20px estimated height) needs resolution boost
        #    so PaddleOCR's DB detector can see individual characters.
        #    We upscale with INTER_CUBIC which preserves text sharpness.
        if p.is_small_text:
            img = self._upscale_for_small_text(img, p)
            p.applied.append(f"upscale_small_text({p.estimated_text_height_px:.0f}px→target)")
            # Update profile dimensions after upscale
            p.height, p.width = img.shape[:2]
            p.is_too_large = max(p.width, p.height) > self.MAX_SIDE

        # 2. Resize if needed (do before other processing to avoid wasted work)
        if p.is_too_large:
            img = self._resize_max(img, self.TARGET_SIDE)
            p.applied.append("resize_down")
        elif p.is_too_small and not p.is_small_text:
            img = self._resize_max(img, self.MIN_SIDE, upscale=True)
            p.applied.append("resize_up")

        # 2b. Noise reduction — only when noise is actually present.
        #    fastNlMeansDenoising works on grayscale. We convert, denoise, convert back.
        #    h parameter controls strength: 10 is conservative, 15 is moderate.
        #    We use 10 to preserve thin text strokes. This is safe for PaddleOCR
        #    because it removes grain without blurring edges (unlike Gaussian blur).
        if p.is_noisy:
            img = self._denoise(img, p.noise_level)
            p.applied.append(f"denoise(sigma={p.noise_level:.1f})")

        # 3. Deskew (do before brightness fixes for better accuracy)
        if p.needs_deskew:
            img = self._deskew(img, p.skew_angle)
            p.applied.append(f"deskew({p.skew_angle:.1f}°)")

        # 3. Shadow / uneven lighting removal
        #    Do BEFORE brightness correction — shadow removal normalizes background
        if p.has_shadow:
            img = self._remove_shadow(img)
            p.applied.append("shadow_removal")
            # Re-measure brightness after shadow removal
            gray_check = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            p.mean_brightness = float(np.mean(gray_check))
            p.is_dark      = p.mean_brightness < self.DARK_MEAN
            p.is_very_dark = p.mean_brightness < self.VERY_DARK_MEAN

        # 4. Brightness correction — dark OR overexposed
        if p.is_very_dark:
            img = self._gamma_correct(img, gamma=0.45)
            p.applied.append("gamma_strong")
        elif p.is_dark:
            img = self._gamma_correct(img, gamma=0.65)
            p.applied.append("gamma_gentle")
        elif p.is_overexposed:
            # Inverse gamma to darken blown-out images.
            # mean > 230 = very overexposed → stronger darkening (gamma 1.8)
            # mean 200-230 = mildly overexposed → gentle darkening (gamma 1.4)
            mean_after = float(np.mean(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)))
            gamma_val = 1.8 if mean_after > 230 else 1.4
            img = self._gamma_correct(img, gamma=gamma_val)
            p.applied.append(f"gamma_darken({gamma_val})")

        # 5. Low contrast (e.g. faded thermal paper)
        #    Only apply CLAHE if image is NOT dark — darkness + CLAHE = noise amplification
        if p.is_low_contrast and not p.is_dark:
            img = self._gentle_clahe(img)
            p.applied.append("clahe")

        return img

    # ── Correction implementations ────────────────────────────────────────────

    def _gamma_correct(self, img: np.ndarray, gamma: float) -> np.ndarray:
        """
        Gamma correction to brighten dark images.
        gamma < 1.0 = brighten (e.g. 0.45 is aggressive, 0.65 is gentle)
        gamma > 1.0 = darken

        This is the right tool for dark images. CLAHE is for low contrast.
        """
        inv_gamma = 1.0 / gamma
        table = np.array([
            (i / 255.0) ** inv_gamma * 255
            for i in range(256)
        ], dtype=np.uint8)
        return cv2.LUT(img, table)

    def _gentle_clahe(self, img: np.ndarray) -> np.ndarray:
        """
        Apply gentle CLAHE only to the L channel of LAB colorspace.
        This enhances contrast without affecting color balance.
        clipLimit=1.5 is deliberately conservative to avoid noise amplification.
        tileGridSize=(16,16) for smoother local adaptation.

        Why gentle: PaddleOCR handles moderate low contrast well.
        We only need to help with severely faded thermal paper.
        """
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        # clipLimit 1.5 (not 2.0+) — gentler, less noise amplification
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(16, 16))
        l = clahe.apply(l)
        lab = cv2.merge([l, a, b])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    def _remove_shadow(self, img: np.ndarray) -> np.ndarray:
        """
        Background normalization to remove shadows and uneven lighting.

        How it works: estimate the background (slow-varying component)
        by heavily dilating then blurring, then divide the original by
        the background. This flattens the illumination gradient.

        Uses a larger kernel (31x31) than the old version (21x21)
        to better capture large shadow gradients across the receipt.
        """
        # Work in LAB to only affect luminance
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        # Estimate background illumination
        dilated = cv2.dilate(l, np.ones((7, 7), np.uint8))
        bg = cv2.medianBlur(dilated, 31)   # was 21 — larger = better shadow coverage

        # Normalize: subtract background, re-center at 200 (keeps image bright)
        norm = cv2.subtract(bg, l)
        norm = 255 - norm  # invert so text stays dark

        # Clip and normalize to full range
        norm = cv2.normalize(norm, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

        lab = cv2.merge([norm, a, b])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    def _deskew(self, img: np.ndarray, angle: float) -> np.ndarray:
        """
        Rotate image to correct skew.
        Uses BORDER_REPLICATE to avoid black corners that confuse OCR.
        Only fires for angles > SKEW_MIN (1.5°) to avoid unnecessary rotation.
        """
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(
            img, M, (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE
        )

    def _resize_max(self, img: np.ndarray, target: int, upscale: bool = False) -> np.ndarray:
        """Resize so the longest side equals target, preserving aspect ratio."""
        h, w = img.shape[:2]
        max_side = max(h, w)
        if not upscale and max_side <= target:
            return img
        if upscale and max_side >= target:
            return img
        scale = target / max_side
        new_w, new_h = int(w * scale), int(h * scale)
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        return cv2.resize(img, (new_w, new_h), interpolation=interp)

    def _upscale_for_small_text(self, img: np.ndarray, p: ImageProfile) -> np.ndarray:
        """
        Upscale image so estimated text height reaches SMALL_TEXT_PX target.
        
        Why INTER_CUBIC and not INTER_LINEAR:
          CUBIC uses 4x4 pixel neighbourhood → smoother interpolation for text strokes
          LINEAR uses 2x2 → faster but leaves more jagged edges on thin characters
          LANCZOS4 is sharper but can introduce ringing on thin strokes
        
        We cap scale at 3.0x to avoid creating absurdly large images.
        """
        h, w = img.shape[:2]
        if p.estimated_text_height_px <= 0:
            return img
        
        # How much do we need to upscale to reach target text height?
        scale = self.SMALL_TEXT_PX / p.estimated_text_height_px
        scale = min(scale, 3.0)   # cap at 3x
        scale = max(scale, 1.1)   # don't bother for tiny adjustments
        
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        # If result would exceed MAX_SIDE, clamp
        max_new = max(new_w, new_h)
        if max_new > self.MAX_SIDE:
            clamp_scale = self.MAX_SIDE / max_new
            new_w = int(new_w * clamp_scale)
            new_h = int(new_h * clamp_scale)
        
        logger.info(
            f"[Preprocessor] Small text upscale: {w}x{h} → {new_w}x{new_h} "
            f"(scale={new_w/w:.2f}x, est text height {p.estimated_text_height_px:.1f}px)"
        )
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    def _measure_noise(self, gray: np.ndarray, h: int, w: int):
        """
        Estimate image noise level using local patch variance.

        Method: divide image into small 8x8 patches, compute variance of each.
        In a clean image, uniform background patches have near-zero variance.
        In a noisy image, even flat areas show high variance from grain.
        We take the 10th percentile of patch variances as our noise estimate —
        this gives us the background noise floor, ignoring text edges.

        Returns: (noise_sigma, is_noisy)
        noise_sigma: estimated standard deviation of noise
        is_noisy: True if sigma exceeds NOISE_THRESHOLD (8.0)

        Why not Gaussian blur check: Laplacian variance detects blur, not noise.
        They are different problems. We need patch variance for noise specifically.
        """
        patch_size = 8
        variances = []
        for y in range(0, h - patch_size, patch_size):
            for x in range(0, w - patch_size, patch_size):
                patch = gray[y:y+patch_size, x:x+patch_size]
                variances.append(float(np.var(patch)))

        if not variances:
            return 0.0, False

        # 10th percentile = background noise floor (avoids text edge patches)
        noise_var = float(np.percentile(variances, 10))
        noise_sigma = float(np.sqrt(max(noise_var, 0)))
        return noise_sigma, noise_sigma > self.NOISE_THRESHOLD

    def _denoise(self, img: np.ndarray, noise_sigma: float) -> np.ndarray:
        """
        Conditional denoising using OpenCV fastNlMeansDenoisingColored.

        Why fastNlMeans and not Gaussian blur:
          Gaussian blur reduces noise BUT also blurs text edges — hurts OCR.
          fastNlMeans uses non-local patch matching to remove grain while
          preserving sharp edges like text strokes. Much safer for OCR input.

        h parameter (filter strength):
          noise_sigma < 12  → h=7  (conservative, preserves detail)
          noise_sigma 12-18 → h=10 (moderate)
          noise_sigma > 18  → h=13 (aggressive, heavy noise)
        We never go above 13 — beyond that, thin receipt text starts dissolving.

        templateWindowSize=7, searchWindowSize=21 are OpenCV defaults and
        work well for receipt-scale images.
        """
        if noise_sigma < 12:
            h_val = 7
        elif noise_sigma < 18:
            h_val = 10
        else:
            h_val = 13

        logger.info(f"[Preprocessor] Denoising: sigma={noise_sigma:.1f} → h={h_val}")

        # fastNlMeansDenoisingColored works on BGR (preserves color for PaddleOCR)
        return cv2.fastNlMeansDenoisingColored(
            img,
            None,
            h=h_val,
            hColor=h_val,
            templateWindowSize=7,
            searchWindowSize=21
        )

    def _detect_perspective(self, img_bgr: np.ndarray):
        """
        Detect if receipt has perspective (trapezoid/keystone) distortion.

        Strategy:
          1. Convert to grayscale, threshold to find dark-on-bright receipt boundary
          2. Find the largest contour (should be the receipt itself)
          3. Approximate to 4 corners using Douglas-Peucker
          4. If we find a clean quadrilateral that is significantly non-rectangular,
             return (True, corner_points) for correction

        Returns: (has_perspective, pts_or_None)

        Conservative criteria — only correct if:
          - We find a clear 4-sided contour
          - The contour covers > 30% of image area (it IS the receipt)
          - The shape deviates from rectangle by > 5% (worth correcting)
        We'd rather skip a mild case than warp a perfectly fine image.
        """
        try:
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape

            # Blur to reduce noise, then threshold
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Find contours
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return False, None

            # Largest contour
            largest = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)

            # Must cover at least 30% of image
            if area < 0.30 * h * w:
                return False, None

            # Approximate to polygon
            peri = cv2.arcLength(largest, True)
            approx = cv2.approxPolyDP(largest, 0.02 * peri, True)

            # Must be a quadrilateral
            if len(approx) != 4:
                return False, None

            pts = approx.reshape(4, 2).astype(np.float32)

            # Check if it's significantly non-rectangular
            # Measure difference between top-width and bottom-width
            # Sort points: top-left, top-right, bottom-right, bottom-left
            rect = self._order_points(pts)
            tl, tr, br, bl = rect
            top_w    = float(np.linalg.norm(tr - tl))
            bottom_w = float(np.linalg.norm(br - bl))
            left_h   = float(np.linalg.norm(bl - tl))
            right_h  = float(np.linalg.norm(br - tr))

            width_ratio  = abs(top_w - bottom_w) / max(top_w, bottom_w)
            height_ratio = abs(left_h - right_h) / max(left_h, right_h)

            # Only correct if distortion > 5% on either axis
            if max(width_ratio, height_ratio) < 0.05:
                return False, None

            logger.info(
                f"[Preprocessor] Perspective detected: "
                f"width_ratio={width_ratio:.2%} height_ratio={height_ratio:.2%}"
            )
            return True, rect

        except Exception as e:
            logger.warning(f"[Preprocessor] Perspective detection failed: {e}")
            return False, None

    def _order_points(self, pts: np.ndarray) -> np.ndarray:
        """
        Order 4 points as: top-left, top-right, bottom-right, bottom-left.
        Used by perspective correction.
        """
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # top-left: smallest x+y
        rect[2] = pts[np.argmax(s)]   # bottom-right: largest x+y
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # top-right: smallest y-x
        rect[3] = pts[np.argmax(diff)]  # bottom-left: largest y-x
        return rect

    def _correct_perspective(self, img: np.ndarray, pts: np.ndarray) -> np.ndarray:
        """
        Apply perspective transform to unwarp a trapezoidal receipt.

        Computes the output dimensions from the detected corner points so
        the result has the correct aspect ratio (not stretched).
        Uses INTER_CUBIC for quality preservation.
        """
        tl, tr, br, bl = pts

        # Output width = max of top and bottom edge lengths
        w_top    = float(np.linalg.norm(tr - tl))
        w_bottom = float(np.linalg.norm(br - bl))
        out_w    = int(max(w_top, w_bottom))

        # Output height = max of left and right edge lengths
        h_left  = float(np.linalg.norm(bl - tl))
        h_right = float(np.linalg.norm(br - tr))
        out_h   = int(max(h_left, h_right))

        dst = np.array([
            [0,         0        ],
            [out_w - 1, 0        ],
            [out_w - 1, out_h - 1],
            [0,         out_h - 1],
        ], dtype=np.float32)

        M = cv2.getPerspectiveTransform(pts, dst)
        warped = cv2.warpPerspective(img, M, (out_w, out_h), flags=cv2.INTER_CUBIC)

        logger.info(f"[Preprocessor] Perspective corrected: {img.shape[1]}x{img.shape[0]} → {out_w}x{out_h}")
        return warped

    def _recommend(self, p: ImageProfile) -> List[str]:
        """Return list of fixes that would be applied, for debugging."""
        fixes = []
        if p.has_perspective:  fixes.append("perspective_correction")
        if p.is_small_text:    fixes.append(f"upscale_small_text({p.estimated_text_height_px:.0f}px)")
        if p.is_too_large:     fixes.append("resize_down")
        if p.is_too_small and not p.is_small_text: fixes.append("resize_up")
        if p.is_noisy:         fixes.append(f"denoise(sigma={p.noise_level:.1f})")
        if p.needs_deskew:     fixes.append(f"deskew({p.skew_angle:.1f}°)")
        if p.has_shadow:       fixes.append("shadow_removal")
        if p.is_very_dark:     fixes.append("gamma_strong(0.45)")
        elif p.is_dark:        fixes.append("gamma_gentle(0.65)")
        elif p.is_overexposed: fixes.append("gamma_darken")
        if p.is_low_contrast and not p.is_dark:
            fixes.append("clahe_gentle")
        if not fixes:          fixes.append("none_needed")
        return fixes


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python image_preprocessor.py <image_path>")
        sys.exit(1)

    path = sys.argv[1]
    pp = ImagePreprocessor()
    print("\n=== Image Quality Analysis ===")
    import json
    quality = pp.analyze_image_quality(path)
    print(json.dumps(quality, indent=2))
    print("\n=== Preprocessing ===")
    out = pp.preprocess(path)
    print(f"Output: {out}")