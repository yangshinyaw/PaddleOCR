"""
Image Stitching for Long Receipts
Combines multiple receipt images into a single image for OCR processing

UPDATED VERSION: Fixed white space gaps and alignment issues
"""

import os
from typing import List, Optional, Tuple
from pathlib import Path
import yaml

import cv2
import numpy as np
from loguru import logger


class ImageStitcher:
    """
    Stitches multiple receipt images together
    
    Features:
    - Vertical stitching for long receipts
    - Feature matching for overlap detection
    - Edge blending for seamless joins
    - Fallback to simple concatenation
    - FIXED: No white space gaps, proper alignment
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize stitcher with configuration"""
        self.config = self._load_config(config_path)
        logger.info("Image Stitcher initialized")
    
    def _load_config(self, config_path: Optional[str] = None):
        """Load configuration"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "ocr_config.yaml"
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config.get('stitching', {})
        except:
            return self._default_config()
    
    def _default_config(self):
        """Default stitching configuration"""
        return {
            'enabled': True,
            'max_parts': 10,
            'overlap_threshold': 0.15,
            'min_match_points': 10,
            'mode': 'vertical',
            'blend_strength': 5
        }
    
    def stitch_images(
        self, 
        image_paths: List[str], 
        output_path: Optional[str] = None,
        method: str = 'auto'
    ) -> Tuple[str, dict]:
        """
        Stitch multiple images together
        
        Args:
            image_paths: List of image file paths (in order)
            output_path: Output file path
            method: 'auto', 'feature_matching', or 'simple_concat'
        
        Returns:
            (output_path, metadata)
        """
        if len(image_paths) < 2:
            raise ValueError("Need at least 2 images to stitch")
        
        if len(image_paths) > self.config.get('max_parts', 10):
            raise ValueError(f"Too many parts (max: {self.config.get('max_parts', 10)})")
        
        logger.info(f"Stitching {len(image_paths)} images using {method} method")
        
        # Load images
        images = []
        for path in image_paths:
            img = cv2.imread(path)
            if img is None:
                raise ValueError(f"Could not read image: {path}")
            images.append(img)
        
        # Choose stitching method
        if method == 'auto':
            # Try feature matching first, fall back to simple concat
            try:
                result_img, metadata = self._stitch_with_features(images)
                metadata['method_used'] = 'feature_matching'
            except Exception as e:
                logger.warning(f"Feature matching failed: {e}, using simple concatenation")
                result_img, metadata = self._simple_concatenate(images)
                metadata['method_used'] = 'simple_concatenation'
        
        elif method == 'feature_matching':
            result_img, metadata = self._stitch_with_features(images)
            metadata['method_used'] = 'feature_matching'
        
        elif method == 'simple_concat':
            result_img, metadata = self._simple_concatenate(images)
            metadata['method_used'] = 'simple_concatenation'
        
        else:
            raise ValueError(f"Unknown stitching method: {method}")
        
        # Save result
        if output_path is None:
            output_dir = Path(__file__).parent.parent / "data" / "temp"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / "stitched_receipt.jpg"
        
        cv2.imwrite(str(output_path), result_img)
        logger.success(f"Stitched image saved: {output_path}")
        
        metadata['output_path'] = str(output_path)
        metadata['num_images'] = len(image_paths)
        
        return str(output_path), metadata
    
    def _stitch_with_features(self, images: List[np.ndarray]) -> Tuple[np.ndarray, dict]:
        """
        Stitch images using feature matching (SIFT/ORB)
        More accurate but slower
        """
        logger.info("Using feature-based stitching")
        
        # Start with first image
        result = images[0]
        total_offset = 0
        matches_info = []
        
        for i in range(1, len(images)):
            logger.debug(f"Stitching image {i+1}/{len(images)}")
            
            # Find overlap between current result and next image
            result, offset, num_matches = self._stitch_pair(result, images[i])
            total_offset += offset
            
            matches_info.append({
                'image_pair': f"{i} -> {i+1}",
                'offset': offset,
                'matches': num_matches
            })
        
        metadata = {
            'total_height': result.shape[0],
            'total_width': result.shape[1],
            'matches_info': matches_info
        }
        
        return result, metadata
    
    def _stitch_pair(self, img1: np.ndarray, img2: np.ndarray) -> Tuple[np.ndarray, int, int]:
        """
        Stitch two images using feature matching
        
        Returns:
            (stitched_image, vertical_offset, num_matches)
        """
        # Convert to grayscale for feature detection
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        
        # Detect features using ORB (faster than SIFT)
        orb = cv2.ORB_create(nfeatures=1000)
        
        kp1, des1 = orb.detectAndCompute(gray1, None)
        kp2, des2 = orb.detectAndCompute(gray2, None)
        
        if des1 is None or des2 is None:
            raise ValueError("Could not detect features in images")
        
        # Match features
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        matches = sorted(matches, key=lambda x: x.distance)
        
        # Check if we have enough good matches
        min_matches = self.config.get('min_match_points', 10)
        good_matches = matches[:50]  # Top 50 matches
        
        if len(good_matches) < min_matches:
            raise ValueError(f"Not enough matches found ({len(good_matches)} < {min_matches})")
        
        # Extract matched points
        pts1 = np.float32([kp1[m.queryIdx].pt for m in good_matches])
        pts2 = np.float32([kp2[m.trainIdx].pt for m in good_matches])
        
        # Calculate average vertical offset
        vertical_offset = int(np.median(pts1[:, 1] - pts2[:, 1]))
        
        logger.debug(f"Found {len(good_matches)} matches, offset: {vertical_offset}px")
        
        # Stitch images with calculated offset
        stitched = self._blend_images_vertical(img1, img2, vertical_offset)
        
        return stitched, vertical_offset, len(good_matches)
    
    def _blend_images_vertical(
        self, 
        img1: np.ndarray, 
        img2: np.ndarray, 
        offset: int
    ) -> np.ndarray:
        """
        Blend two images vertically with smooth transition
        
        Args:
            img1: Top image
            img2: Bottom image
            offset: Vertical overlap (negative means img2 starts higher)
        """
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]
        
        # Calculate output dimensions
        max_width = max(w1, w2)
        
        if offset >= 0:
            # Normal overlap: img2 starts after img1
            total_height = h1 + h2 - offset
            img2_start = h1 - offset
        else:
            # Negative overlap: gap between images
            total_height = h1 + h2 + abs(offset)
            img2_start = h1 + abs(offset)
        
        # Create output canvas
        result = np.zeros((total_height, max_width, 3), dtype=np.uint8)
        result.fill(255)  # White background
        
        # Place first image
        result[0:h1, 0:w1] = img1
        
        # Blend region
        blend_strength = self.config.get('blend_strength', 5)
        
        if offset > 0 and offset < min(h1, h2):
            # Calculate blend region
            blend_start = h1 - offset
            blend_height = min(offset, h2)
            
            # Create blend mask (gradient)
            mask = np.linspace(1, 0, blend_height).reshape(-1, 1)
            mask = np.tile(mask, (1, max_width, 3))
            
            # Blend in overlap region
            region1 = result[blend_start:blend_start+blend_height, 0:w1]
            region2 = img2[0:blend_height, 0:w2]
            
            # Resize region2 if widths don't match
            if w2 < max_width:
                region2_padded = np.zeros((blend_height, max_width, 3), dtype=np.uint8)
                region2_padded.fill(255)
                region2_padded[:, 0:w2] = region2
                region2 = region2_padded
            
            blended = (region1 * mask + region2 * (1 - mask)).astype(np.uint8)
            result[blend_start:blend_start+blend_height, 0:max_width] = blended
            
            # Place rest of img2
            if blend_height < h2:
                result[blend_start+blend_height:blend_start+h2, 0:w2] = img2[blend_height:h2, 0:w2]
        else:
            # No overlap, just place img2
            result[img2_start:img2_start+h2, 0:w2] = img2
        
        return result
    
    def _simple_concatenate(self, images: List[np.ndarray]) -> Tuple[np.ndarray, dict]:
        """
        Simple vertical concatenation with proper alignment and overlap removal
        
        IMPROVEMENTS:
        - Resize images to same width (no white padding)
        - Detect and remove overlap between images
        - Clean alignment without gaps
        """
        logger.info("Using simple concatenation with alignment")
        
        # Get dimensions
        heights = [img.shape[0] for img in images]
        widths = [img.shape[1] for img in images]
        max_width = max(widths)
        min_width = min(widths)
        
        # Strategy: Resize all images to same width (avoid padding)
        # Use the maximum width as target
        target_width = max_width
        
        logger.info(f"Resizing all images to width: {target_width}px")
        
        resized_images = []
        for img in images:
            h, w = img.shape[:2]
            if w != target_width:
                # Resize to match target width, maintain aspect ratio
                new_height = int(h * (target_width / w))
                img_resized = cv2.resize(img, (target_width, new_height), interpolation=cv2.INTER_CUBIC)
                resized_images.append(img_resized)
                logger.debug(f"Resized image from {w}x{h} to {target_width}x{new_height}")
            else:
                resized_images.append(img)
        
        # Detect and remove overlap between consecutive images
        final_images = [resized_images[0]]
        total_overlap = 0
        
        for i in range(1, len(resized_images)):
            prev_img = final_images[-1]
            curr_img = resized_images[i]
            
            # Detect overlap by comparing bottom of previous with top of current
            overlap_px = self._detect_overlap_pixels(prev_img, curr_img)
            
            if overlap_px > 0:
                logger.info(f"Detected {overlap_px}px overlap, removing...")
                # Crop the overlapping part from current image
                curr_img = curr_img[overlap_px:, :]
                total_overlap += overlap_px
            
            final_images.append(curr_img)
        
        # Concatenate vertically
        result = np.vstack(final_images)
        
        metadata = {
            'total_height': result.shape[0],
            'total_width': result.shape[1],
            'concatenation': 'simple_vertical_aligned',
            'overlap_removed_px': total_overlap,
            'resize_method': 'aspect_ratio_preserved'
        }
        
        logger.success(f"Stitched result: {result.shape[1]}x{result.shape[0]}px, removed {total_overlap}px overlap")
        
        return result, metadata
    
    def _detect_overlap_pixels(self, img1: np.ndarray, img2: np.ndarray) -> int:
        """
        Detect how many pixels of overlap exist between two images
        
        Compares bottom of img1 with top of img2 to find matching region
        
        Args:
            img1: First image (bottom part will be compared)
            img2: Second image (top part will be compared)
        
        Returns:
            Number of overlapping pixels (0 if no overlap detected)
        """
        h1 = img1.shape[0]
        h2 = img2.shape[0]
        
        # Maximum overlap to check (don't check more than 30% of smaller image)
        max_overlap = min(int(h1 * 0.3), int(h2 * 0.3), 200)
        
        if max_overlap < 10:
            return 0
        
        best_overlap = 0
        best_similarity = 0
        
        # Check different overlap amounts
        for overlap in range(10, max_overlap, 5):
            try:
                # Get bottom section of img1
                section1 = img1[-overlap:, :]
                # Get top section of img2
                section2 = img2[:overlap, :]
                
                # Ensure same dimensions
                if section1.shape != section2.shape:
                    continue
                
                # Calculate similarity using absolute difference
                diff = cv2.absdiff(section1, section2)
                similarity = 1 - (np.mean(diff) / 255)
                
                # If similarity is high, this is likely the overlap
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_overlap = overlap
                    
            except Exception as e:
                logger.debug(f"Error checking overlap at {overlap}px: {e}")
                continue
        
        # Only return overlap if similarity is high enough (70%+)
        if best_similarity > 0.70:
            logger.debug(f"Found overlap: {best_overlap}px with {best_similarity:.1%} similarity")
            return best_overlap
        
        logger.debug(f"No significant overlap detected (best similarity: {best_similarity:.1%})")
        return 0
    
    def detect_long_receipt(self, image_path: str) -> bool:
        """
        Detect if an image is likely part of a long receipt
        
        Args:
            image_path: Path to image
        
        Returns:
            True if likely a partial receipt that needs stitching
        """
        img = cv2.imread(image_path)
        if img is None:
            return False
        
        h, w = img.shape[:2]
        aspect_ratio = h / w
        
        # Long receipts typically have high aspect ratio (height >> width)
        # But partial scans might have lower ratio
        
        # Check for cut-off text at edges (simple heuristic)
        # In a real implementation, you'd use OCR to detect partial text
        
        # For now, just check aspect ratio
        return aspect_ratio > 3.0  # Very tall image


def main():
    """Test the stitcher"""
    logger.add("logs/stitcher_test.log", rotation="10 MB")
    
    print("\n" + "="*60)
    print("Image Stitcher - Test Run")
    print("="*60 + "\n")
    
    stitcher = ImageStitcher()
    
    # Check for sample images
    sample_dir = Path("data/sample_receipts")
    sample_images = list(sample_dir.glob("*.jpg")) + list(sample_dir.glob("*.png"))
    
    if len(sample_images) < 2:
        print("⚠️  Need at least 2 sample images to test stitching")
        print("Add multiple receipt images to data/sample_receipts/")
        print("\nFor testing, you can:")
        print("1. Take photos of the same receipt in 2 parts")
        print("2. Split an existing receipt image in half")
        return
    
    # Use first two images for testing
    test_images = [str(img) for img in sample_images[:2]]
    print(f"Testing with {len(test_images)} images:\n")
    for i, img in enumerate(test_images, 1):
        print(f"  {i}. {Path(img).name}")
    
    print("\n" + "-"*60)
    print("Method 1: Auto (feature matching with fallback)")
    print("-"*60)
    try:
        output_path, metadata = stitcher.stitch_images(test_images, method='auto')
        print(f"\n✅ Success!")
        print(f"Output: {output_path}")
        print(f"Method used: {metadata['method_used']}")
        print(f"Dimensions: {metadata['total_width']}x{metadata['total_height']}")
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    print("\n" + "-"*60)
    print("Method 2: Simple Concatenation")
    print("-"*60)
    try:
        output_path, metadata = stitcher.stitch_images(test_images, method='simple_concat')
        print(f"\n✅ Success!")
        print(f"Output: {output_path}")
        print(f"Dimensions: {metadata['total_width']}x{metadata['total_height']}")
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    print("\n" + "="*60)
    print("Stitching tests complete!")
    print("Check data/temp/ for stitched images")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()