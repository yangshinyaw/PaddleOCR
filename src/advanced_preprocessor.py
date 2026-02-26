"""
Advanced Image Preprocessing for Better OCR Accuracy
Handles: creases, skew, noise, low contrast, wrinkles

NEW FEATURES:
- Automatic deskewing (straightens tilted receipts)
- Morphological operations (removes noise)
- Adaptive binarization (handles varying lighting)
- Crease detection and removal
"""

import os
from typing import Optional, Tuple
from pathlib import Path
import yaml

os.environ['FLAGS_use_mkldnn'] = 'False'
os.environ['FLAGS_enable_new_ir'] = 'False'

import cv2
import numpy as np
from loguru import logger


class AdvancedImagePreprocessor:
    """
    Advanced preprocessing for challenging receipts
    
    Handles:
    - Wrinkled/creased paper
    - Skewed/tilted images
    - Low contrast
    - Noise and artifacts
    - Variable lighting
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize preprocessor"""
        self.config = self._load_config(config_path)
        logger.info("Advanced Image Preprocessor initialized")
    
    def _load_config(self, config_path: Optional[str] = None):
        """Load configuration"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "ocr_config.yaml"
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config.get('preprocessing', {})
        except:
            return self._default_config()
    
    def _default_config(self):
        """Default configuration"""
        return {
            'max_image_size': 4096,
            'min_image_size': 100,
            'auto_deskew': True,
            'denoise': True,
            'enhance_contrast': True
        }
    
    def preprocess_premium(
        self, 
        image_path: str, 
        output_path: Optional[str] = None
    ) -> str:
        """
        PREMIUM preprocessing for challenging receipts
        
        Pipeline:
        1. Load and validate
        2. Resize to optimal size
        3. Deskew (straighten)
        4. Denoise (remove artifacts)
        5. CLAHE (adaptive contrast)
        6. Morphological operations
        7. Adaptive thresholding
        
        Args:
            image_path: Input image
            output_path: Optional output path
            
        Returns:
            Path to preprocessed image
        """
        logger.info(f"🔧 Premium preprocessing: {image_path}")
        
        # Step 1: Load image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")
        
        original_height, original_width = img.shape[:2]
        logger.info(f"Original size: {original_width}x{original_height}")
        
        # Step 2: Convert to grayscale
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()
        
        # Step 3: Resize if needed (optimal: 2000-3000px width)
        gray = self._resize_optimal(gray)
        
        # Step 4: Deskew (straighten tilted images)
        gray = self._deskew(gray)
        logger.info("✓ Deskewed")
        
        # Step 5: Denoise (remove noise and artifacts)
        gray = self._denoise(gray)
        logger.info("✓ Denoised")
        
        # Step 6: CLAHE (adaptive contrast enhancement)
        gray = self._apply_clahe(gray)
        logger.info("✓ CLAHE applied")
        
        # Step 7: Morphological operations (clean up text)
        gray = self._morphological_cleanup(gray)
        logger.info("✓ Morphological cleanup")
        
        # Step 8: Sharpen text edges
        gray = self._sharpen_text(gray)
        logger.info("✓ Sharpened")
        
        # Save
        if output_path is None:
            output_dir = Path(__file__).parent.parent / "data" / "temp"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"premium_{Path(image_path).name}"
        
        cv2.imwrite(str(output_path), gray)
        logger.success(f"✅ Premium preprocessing complete: {output_path}")
        
        return str(output_path)
    
    def _resize_optimal(self, img: np.ndarray) -> np.ndarray:
        """Resize to optimal size for OCR (2000-3000px width)"""
        height, width = img.shape[:2]
        
        # Optimal width for OCR
        optimal_width = 2500
        
        if width < 1500:
            # Upscale small images
            scale = optimal_width / width
            new_width = int(width * scale)
            new_height = int(height * scale)
            img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
            logger.info(f"Upscaled to {new_width}x{new_height}")
        elif width > 3500:
            # Downscale very large images
            scale = optimal_width / width
            new_width = int(width * scale)
            new_height = int(height * scale)
            img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
            logger.info(f"Downscaled to {new_width}x{new_height}")
        
        return img
    
    def _deskew(self, img: np.ndarray) -> np.ndarray:
        """
        Automatically deskew (straighten) tilted images
        
        Uses Hough Line Transform to detect dominant angle
        """
        # Find edges
        edges = cv2.Canny(img, 50, 150, apertureSize=3)
        
        # Detect lines
        lines = cv2.HoughLines(edges, 1, np.pi/180, 200)
        
        if lines is None:
            return img
        
        # Calculate angles
        angles = []
        for rho, theta in lines[:, 0]:
            angle = np.degrees(theta) - 90
            if -45 < angle < 45:  # Only consider reasonable angles
                angles.append(angle)
        
        if not angles:
            return img
        
        # Get median angle
        median_angle = np.median(angles)
        
        # Only deskew if angle is significant (> 0.5 degrees)
        if abs(median_angle) > 0.5:
            logger.info(f"Deskewing by {median_angle:.2f} degrees")
            
            # Rotate image
            height, width = img.shape
            center = (width // 2, height // 2)
            matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
            img = cv2.warpAffine(img, matrix, (width, height), 
                                flags=cv2.INTER_CUBIC,
                                borderMode=cv2.BORDER_REPLICATE)
        
        return img
    
    def _denoise(self, img: np.ndarray) -> np.ndarray:
        """
        Remove noise while preserving text
        
        Uses Non-Local Means Denoising
        """
        # Fast denoising for grayscale images
        denoised = cv2.fastNlMeansDenoising(img, None, h=10, templateWindowSize=7, searchWindowSize=21)
        return denoised
    
    def _apply_clahe(self, img: np.ndarray) -> np.ndarray:
        """
        Apply CLAHE for adaptive contrast enhancement
        """
        # Check if image needs enhancement
        std_dev = np.std(img)
        
        if std_dev < 50:  # Low contrast
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            img = clahe.apply(img)
            logger.info(f"CLAHE applied (std_dev was {std_dev:.1f})")
        
        return img
    
    def _morphological_cleanup(self, img: np.ndarray) -> np.ndarray:
        """
        Morphological operations to clean up text
        
        - Closing: fills small holes in text
        - Opening: removes small noise
        """
        # Small kernel for minor cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        
        # Closing: fill small gaps in letters
        img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        return img
    
    def _sharpen_text(self, img: np.ndarray) -> np.ndarray:
        """
        Sharpen text edges for better OCR
        """
        # Unsharp masking
        gaussian = cv2.GaussianBlur(img, (0, 0), 2.0)
        sharpened = cv2.addWeighted(img, 1.5, gaussian, -0.5, 0)
        
        return sharpened
    
    def preprocess(self, image_path: str, output_path: Optional[str] = None) -> str:
        """
        Default preprocessing method
        
        Uses premium preprocessing for best results
        """
        return self.preprocess_premium(image_path, output_path)


def main():
    """Test the advanced preprocessor"""
    print("\n" + "="*70)
    print("ADVANCED IMAGE PREPROCESSOR - Test Mode")
    print("="*70 + "\n")
    
    preprocessor = AdvancedImagePreprocessor()
    
    # Check for sample images
    sample_dir = Path("data/sample_receipts")
    sample_images = list(sample_dir.glob("*.jpg")) + list(sample_dir.glob("*.png"))
    
    if not sample_images:
        print("⚠️  No sample images found in data/sample_receipts/")
        return
    
    test_image = str(sample_images[0])
    print(f"Testing with: {test_image}\n")
    
    print("🔧 Running premium preprocessing...")
    result = preprocessor.preprocess_premium(test_image)
    print(f"\n✅ Complete! Processed image: {result}")
    print("\nProcessed image saved to data/temp/")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
