"""
Image Preprocessing Pipeline for Receipt OCR
Handles image enhancement, rotation correction, and optimization
"""

import os
from typing import Tuple, Optional
from pathlib import Path
import yaml

# Fix for Windows OneDNN compatibility issue
os.environ['FLAGS_use_mkldnn'] = 'False'
os.environ['FLAGS_enable_new_ir'] = 'False'

import cv2
import numpy as np
from PIL import Image, ImageEnhance
from loguru import logger


class ImagePreprocessor:
    """
    Preprocesses receipt images for optimal OCR results
    
    Features:
    - Automatic rotation detection and correction
    - Contrast and brightness enhancement
    - Noise reduction
    - Resolution optimization
    - Format conversion
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize preprocessor with configuration"""
        self.config = self._load_config(config_path)
        logger.info("Image Preprocessor initialized")
    
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
        """Default preprocessing configuration"""
        return {
            'auto_rotate': True,
            'denoise': True,
            'enhance_contrast': True,
            'max_image_size': 4096,
            'min_image_size': 100
        }
    
    def preprocess(self, image_path: str, output_path: Optional[str] = None) -> str:
        """
        Complete preprocessing pipeline
        
        Args:
            image_path: Input image path
            output_path: Optional output path (defaults to temp directory)
        
        Returns:
            Path to preprocessed image
        """
        logger.info(f"Preprocessing image: {image_path}")
        
        # Read image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")
        
        original_shape = img.shape
        logger.debug(f"Original size: {original_shape[1]}x{original_shape[0]}")
        
        # Step 1: Resize if needed
        img = self._resize_if_needed(img)
        
        # Step 2: Auto-rotate if enabled
        if self.config.get('auto_rotate', True):
            img = self._auto_rotate(img)
        
        # Step 3: Denoise if enabled
        if self.config.get('denoise', True):
            img = self._denoise(img)
        
        # Step 4: Enhance contrast if enabled
        if self.config.get('enhance_contrast', True):
            img = self._enhance_contrast(img)
        
        # Step 5: Sharpen
        img = self._sharpen(img)
        
        # Save preprocessed image
        if output_path is None:
            output_dir = Path(__file__).parent.parent / "data" / "temp"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"preprocessed_{Path(image_path).name}"
        
        cv2.imwrite(str(output_path), img)
        logger.success(f"Preprocessed image saved: {output_path}")
        
        return str(output_path)
    
    def _resize_if_needed(self, img: np.ndarray) -> np.ndarray:
        """Resize image if it exceeds size limits"""
        height, width = img.shape[:2]
        max_size = self.config.get('max_image_size', 4096)
        
        if width > max_size or height > max_size:
            # Calculate scaling factor
            scale = max_size / max(width, height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            
            img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
            logger.info(f"Resized to {new_width}x{new_height}")
        
        return img
    
    def _auto_rotate(self, img: np.ndarray) -> np.ndarray:
        """
        Automatically detect and correct image rotation
        Uses Hough Line Transform to detect text orientation
        """
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Edge detection
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            
            # Detect lines
            lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
            
            if lines is not None and len(lines) > 0:
                # Calculate average angle
                angles = []
                for line in lines[:50]:  # Use first 50 lines
                    rho, theta = line[0]
                    angle = np.degrees(theta) - 90
                    if -45 < angle < 45:
                        angles.append(angle)
                
                if angles:
                    median_angle = np.median(angles)
                    
                    # Only rotate if angle is significant
                    if abs(median_angle) > 0.5:
                        logger.info(f"Rotating image by {median_angle:.2f} degrees")
                        img = self._rotate_image(img, median_angle)
        
        except Exception as e:
            logger.warning(f"Auto-rotation failed: {e}, skipping rotation")
        
        return img
    
    def _rotate_image(self, img: np.ndarray, angle: float) -> np.ndarray:
        """Rotate image by given angle"""
        height, width = img.shape[:2]
        center = (width // 2, height // 2)
        
        # Get rotation matrix
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        # Calculate new dimensions
        cos = np.abs(matrix[0, 0])
        sin = np.abs(matrix[0, 1])
        new_width = int((height * sin) + (width * cos))
        new_height = int((height * cos) + (width * sin))
        
        # Adjust rotation matrix for new dimensions
        matrix[0, 2] += (new_width / 2) - center[0]
        matrix[1, 2] += (new_height / 2) - center[1]
        
        # Perform rotation
        rotated = cv2.warpAffine(img, matrix, (new_width, new_height), 
                                 borderValue=(255, 255, 255))
        
        return rotated
    
    def _denoise(self, img: np.ndarray) -> np.ndarray:
        """
        Remove noise from image
        Uses Non-Local Means Denoising
        """
        try:
            # Apply denoising
            denoised = cv2.fastNlMeansDenoisingColored(
                img, 
                None, 
                h=10,  # Filter strength
                hColor=10,
                templateWindowSize=7,
                searchWindowSize=21
            )
            logger.debug("Denoising applied")
            return denoised
        except Exception as e:
            logger.warning(f"Denoising failed: {e}")
            return img
    
    def _enhance_contrast(self, img: np.ndarray) -> np.ndarray:
        """
        Enhance image contrast using CLAHE
        (Contrast Limited Adaptive Histogram Equalization)
        """
        try:
            # Convert to LAB color space
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply CLAHE to L channel
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            
            # Merge channels
            lab = cv2.merge([l, a, b])
            
            # Convert back to BGR
            enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
            logger.debug("Contrast enhancement applied")
            
            return enhanced
        except Exception as e:
            logger.warning(f"Contrast enhancement failed: {e}")
            return img
    
    def _sharpen(self, img: np.ndarray) -> np.ndarray:
        """Sharpen image to enhance text clarity"""
        try:
            # Sharpening kernel
            kernel = np.array([[-1, -1, -1],
                              [-1,  9, -1],
                              [-1, -1, -1]])
            
            sharpened = cv2.filter2D(img, -1, kernel)
            logger.debug("Sharpening applied")
            
            return sharpened
        except Exception as e:
            logger.warning(f"Sharpening failed: {e}")
            return img
    
    def convert_to_grayscale(self, image_path: str, output_path: Optional[str] = None) -> str:
        """Convert image to grayscale for better OCR in some cases"""
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        if output_path is None:
            output_dir = Path(__file__).parent.parent / "data" / "temp"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"gray_{Path(image_path).name}"
        
        cv2.imwrite(str(output_path), gray)
        return str(output_path)
    
    def adaptive_threshold(self, image_path: str, output_path: Optional[str] = None) -> str:
        """
        Apply adaptive thresholding - useful for receipts with varying lighting
        """
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        
        # Apply adaptive threshold
        thresh = cv2.adaptiveThreshold(
            img, 
            255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 
            11, 
            2
        )
        
        if output_path is None:
            output_dir = Path(__file__).parent.parent / "data" / "temp"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"thresh_{Path(image_path).name}"
        
        cv2.imwrite(str(output_path), thresh)
        logger.info(f"Adaptive threshold applied: {output_path}")
        
        return str(output_path)
    
    def remove_shadows(self, image_path: str, output_path: Optional[str] = None) -> str:
        """Remove shadows from receipt images"""
        img = cv2.imread(image_path)
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply morphological operations
        dilated = cv2.dilate(gray, np.ones((7, 7), np.uint8))
        bg = cv2.medianBlur(dilated, 21)
        
        # Difference
        diff = 255 - cv2.absdiff(gray, bg)
        
        # Normalize
        norm = cv2.normalize(diff, None, alpha=0, beta=255, 
                            norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        
        if output_path is None:
            output_dir = Path(__file__).parent.parent / "data" / "temp"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"no_shadow_{Path(image_path).name}"
        
        cv2.imwrite(str(output_path), norm)
        logger.info(f"Shadows removed: {output_path}")
        
        return str(output_path)


def main():
    """Test the preprocessor"""
    logger.add("logs/preprocessor_test.log", rotation="10 MB")
    
    print("\n" + "="*60)
    print("Image Preprocessor - Test Run")
    print("="*60 + "\n")
    
    preprocessor = ImagePreprocessor()
    
    # Check for sample images
    sample_dir = Path("data/sample_receipts")
    sample_images = list(sample_dir.glob("*.jpg")) + list(sample_dir.glob("*.png"))
    
    if not sample_images:
        print("⚠️  No sample images found in data/sample_receipts/")
        return
    
    test_image = str(sample_images[0])
    print(f"Testing with: {test_image}\n")
    
    # Test preprocessing
    print("Running preprocessing pipeline...")
    processed = preprocessor.preprocess(test_image)
    print(f"✅ Preprocessed: {processed}\n")
    
    # Test additional methods
    print("Testing additional preprocessing methods...")
    
    gray_path = preprocessor.convert_to_grayscale(test_image)
    print(f"✅ Grayscale: {gray_path}")
    
    thresh_path = preprocessor.adaptive_threshold(test_image)
    print(f"✅ Adaptive threshold: {thresh_path}")
    
    shadow_path = preprocessor.remove_shadows(test_image)
    print(f"✅ Shadow removal: {shadow_path}")
    
    print("\n" + "="*60)
    print("All preprocessing tests complete!")
    print("Check data/temp/ for processed images")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()