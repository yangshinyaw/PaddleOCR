"""
Integrated Receipt Processing Pipeline
Combines preprocessing, stitching, and OCR into a unified workflow
"""

import os
from typing import List, Optional, Dict
from pathlib import Path

# Fix for Windows OneDNN compatibility issue
os.environ['FLAGS_use_mkldnn'] = 'False'
os.environ['FLAGS_enable_new_ir'] = 'False'

from loguru import logger

from ocr_engine import OCREngine
from image_preprocessor import ImagePreprocessor
from image_stitcher import ImageStitcher
from utils import (
    validate_image_file,
    sanitize_filename,
    ensure_directory,
    merge_ocr_results,
    extract_receipt_metadata,
    setup_logging
)

# Smart metadata extractor — handles Mercury Drug, SM, and all PH stores
try:
    from general_metadata_extractor import GeneralMetadataExtractor as _GME
    _metadata_extractor = _GME()
    logger.info("GeneralMetadataExtractor loaded OK")
except Exception:
    _metadata_extractor = None

# Rotation corrector — only used when fix_rotation=True (opt-in, zero cost when off)
try:
    from image_rotation_corrector import ImageRotationCorrector as _IRC
    logger.info("ImageRotationCorrector loaded OK")
except Exception as _rot_err:
    logger.warning(f"ImageRotationCorrector not available: {_rot_err}")
    _IRC = None


class ReceiptProcessor:
    """
    End-to-end receipt processing pipeline
    
    Workflow:
    1. Validate input images
    2. Preprocess (enhance, denoise, rotate)
    3. Stitch if multiple parts
    4. Extract text with OCR
    5. Parse structured data
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize all processing components"""
        logger.info("Initializing Receipt Processor Pipeline")
        
        self.ocr_engine = OCREngine(config_path)
        self.preprocessor = ImagePreprocessor(config_path)
        self.stitcher = ImageStitcher(config_path)
        
        # Create temp directory
        self.temp_dir = Path("data/temp")
        ensure_directory(str(self.temp_dir))

        # Rotation corrector — shares the OCR engine for Pass 2 spatial analysis
        self.rotation_corrector = None
        if _IRC is not None:
            self.rotation_corrector = _IRC(ocr_engine=self.ocr_engine)

        logger.success("Receipt Processor ready")
    
    def process_single_image(
        self,
        image_path: str,
        preprocess: bool = True,
        extract_metadata: bool = False,
        fix_rotation: bool = False
    ) -> Dict:
        """
        Process a single receipt image.

        Args:
            image_path:       Path to receipt image
            preprocess:       Apply preprocessing pipeline
            extract_metadata: Extract structured data (merchant, total, items, etc.)
            fix_rotation:     Detect and correct 90°/180°/270° rotations (~200ms).
                              Default False — zero cost when disabled.

        Returns:
            Processing result dictionary
        """
        logger.info(f"Processing single image: {image_path}")

        # Validate
        is_valid, msg = validate_image_file(image_path)
        if not is_valid:
            return {
                'status': 'error',
                'error': f"Invalid image: {msg}",
                'image_path': image_path
            }

        rotation_degrees = 0
        rotation_temp    = None  # track temp file for cleanup

        try:
            working_path = image_path

            # ── Step 0: Rotation correction (opt-in, runs BEFORE preprocess) ─
            if fix_rotation and self.rotation_corrector is not None:
                logger.info("[Rotation] Checking orientation...")
                corrected_path, rotation_degrees = \
                    self.rotation_corrector.detect_and_correct(working_path)
                if rotation_degrees != 0:
                    working_path  = corrected_path
                    rotation_temp = corrected_path  # remember for cleanup
                    logger.info(f"[Rotation] Pass1/2 applied {rotation_degrees}°")

            # ── Step 1: Preprocess ────────────────────────────────────────────
            if preprocess:
                logger.info("Applying preprocessing...")
                working_path = self.preprocessor.preprocess(working_path)

            # ── Step 2: OCR ───────────────────────────────────────────────────
            logger.info("Extracting text with OCR...")
            result = self.ocr_engine.extract_text(
                working_path,
                return_confidence=True,
                return_positions=True
            )

            # ── Step 3: Metadata + Pass 3 rotation check ─────────────────────
            if extract_metadata and result.get('status') == 'success':
                text_lines = [line['text'] for line in result['lines']]

                # Pass 3: post-OCR line-order check for upside-down
                # Only run if fix_rotation enabled and Pass 1/2 found nothing
                if fix_rotation and rotation_degrees == 0 and \
                        self.rotation_corrector is not None:
                    text_rot = self.rotation_corrector.check_text_orientation(
                        text_lines
                    )
                    if text_rot != 0:
                        logger.info(
                            f"[Rotation] Pass3 detected {text_rot}° — re-running OCR"
                        )
                        import cv2 as _cv2
                        # Re-read the preprocessed (or original) image and rotate
                        src = _cv2.imread(working_path)
                        rotated = _cv2.rotate(src, {
                            90:  _cv2.ROTATE_90_CLOCKWISE,
                            180: _cv2.ROTATE_180,
                            270: _cv2.ROTATE_90_COUNTERCLOCKWISE,
                        }[text_rot])
                        import tempfile as _tf, os as _os
                        fd, rerun_path = _tf.mkstemp(suffix=".jpg")
                        _os.close(fd)
                        try:
                            _cv2.imwrite(rerun_path, rotated)
                            result2 = self.ocr_engine.extract_text(
                                rerun_path,
                                return_confidence=True,
                                return_positions=True
                            )
                            if result2.get("status") == "success":
                                result       = result2
                                text_lines   = [l['text'] for l in result['lines']]
                                rotation_degrees = text_rot
                                logger.info(
                                    f"[Rotation] Pass3 re-run OK, "
                                    f"{len(text_lines)} lines"
                                )
                        finally:
                            try:
                                Path(rerun_path).unlink(missing_ok=True)
                            except Exception:
                                pass

                # Extract metadata
                if _metadata_extractor is not None:
                    metadata = _metadata_extractor.extract(text_lines)
                else:
                    metadata = extract_receipt_metadata(text_lines)

                metadata['rotation_applied'] = rotation_degrees
                result['metadata'] = metadata

            result['image_path']      = image_path
            result['rotation_applied'] = rotation_degrees
            return result

        finally:
            # Clean up rotation temp file (created by detect_and_correct)
            if rotation_temp and rotation_temp != image_path:
                try:
                    Path(rotation_temp).unlink(missing_ok=True)
                except Exception:
                    pass
    
    def process_multiple_images(
        self,
        image_paths: List[str],
        stitch: bool = True,
        preprocess: bool = True,
        extract_metadata: bool = False,
        fix_rotation: bool = False
    ) -> Dict:
        """
        Process multiple receipt images (long receipt parts).

        Args:
            image_paths:      List of image paths (in order)
            stitch:           Stitch images together first
            preprocess:       Apply preprocessing
            extract_metadata: Extract structured data
            fix_rotation:     Detect and correct rotations per image

        Returns:
            Processing result dictionary
        """
        logger.info(f"Processing {len(image_paths)} images")
        
        # Validate all images
        for path in image_paths:
            is_valid, msg = validate_image_file(path)
            if not is_valid:
                return {
                    'status': 'error',
                    'error': f"Invalid image {path}: {msg}"
                }

        rotation_temps = []

        # Step 0: Rotation correction per image (opt-in, runs BEFORE preprocess)
        if fix_rotation and self.rotation_corrector is not None:
            logger.info("[Rotation] Checking orientation of all images...")
            corrected_paths = []
            for path in image_paths:
                corrected, deg = self.rotation_corrector.detect_and_correct(path)
                corrected_paths.append(corrected)
                if deg != 0:
                    rotation_temps.append(corrected)
                    logger.info(
                        f"[Rotation] {Path(path).name}: {deg}° corrected"
                    )
            image_paths = corrected_paths

        # Preprocess if requested
        if preprocess:
            logger.info("Preprocessing all images...")
            preprocessed_paths = []
            for path in image_paths:
                preprocessed = self.preprocessor.preprocess(path)
                preprocessed_paths.append(preprocessed)
            image_paths = preprocessed_paths
        
        # Stitch if requested and multiple images
        if stitch and len(image_paths) > 1:
            logger.info("Stitching images...")
            try:
                stitched_path, stitch_metadata = self.stitcher.stitch_images(
                    image_paths,
                    method='auto'
                )
                
                # Process stitched image
                result = self.ocr_engine.extract_text(
                    stitched_path,
                    return_confidence=True,
                    return_positions=True
                )
                result['stitching'] = stitch_metadata
                result['image_path'] = stitched_path
                
            except Exception as e:
                logger.warning(f"Stitching failed: {e}, processing individually")
                # Fallback: process individually and merge
                results = []
                for path in image_paths:
                    res = self.ocr_engine.extract_text(path)
                    results.append(res)
                
                result = merge_ocr_results(results)
                result['stitching'] = {'status': 'failed', 'error': str(e)}
        else:
            # Process all images individually
            results = []
            for path in image_paths:
                res = self.ocr_engine.extract_text(path)
                results.append(res)
            
            result = merge_ocr_results(results)
        
        # Extract metadata if requested
        if extract_metadata and result.get('status') == 'success':
            text_lines = [line['text'] for line in result['lines']]
            if _metadata_extractor is not None:
                metadata = _metadata_extractor.extract(text_lines)
            else:
                metadata = extract_receipt_metadata(text_lines)
            # rotation_applied=0 here: per-image corrections already happened above
            metadata['rotation_applied'] = 0
            result['metadata'] = metadata

        # Clean up rotation temp files
        for tmp in rotation_temps:
            try:
                Path(tmp).unlink(missing_ok=True)
            except Exception:
                pass

        return result
    
    def process_directory(
        self,
        directory: str,
        pattern: str = "*.jpg"
    ) -> List[Dict]:
        """
        Process all images in a directory
        
        Args:
            directory: Directory path
            pattern: File pattern (e.g., "*.jpg", "*.png")
        
        Returns:
            List of processing results
        """
        logger.info(f"Processing directory: {directory}")
        
        dir_path = Path(directory)
        if not dir_path.exists():
            return [{
                'status': 'error',
                'error': f"Directory not found: {directory}"
            }]
        
        # Find all matching images
        image_files = sorted(dir_path.glob(pattern))
        
        if not image_files:
            logger.warning(f"No images found matching pattern: {pattern}")
            return []
        
        logger.info(f"Found {len(image_files)} images")
        
        # Process each image
        results = []
        for i, img_path in enumerate(image_files, 1):
            logger.info(f"Processing {i}/{len(image_files)}: {img_path.name}")
            
            result = self.process_single_image(str(img_path))
            result['filename'] = img_path.name
            results.append(result)
        
        return results
    
    def quick_text_extract(self, image_path: str) -> List[str]:
        """
        Quick helper to just get text lines (no metadata)
        
        Args:
            image_path: Path to image
        
        Returns:
            List of text strings
        """
        result = self.process_single_image(
            image_path,
            preprocess=True,
            extract_metadata=False
        )
        
        if result.get('status') == 'success':
            return [line['text'] for line in result.get('lines', [])]
        else:
            return []


def main():
    """Demo the integrated pipeline"""
    setup_logging(level="INFO")
    
    print("\n" + "="*60)
    print("Receipt Processing Pipeline - Demo")
    print("="*60 + "\n")
    
    # Initialize pipeline
    processor = ReceiptProcessor()
    
    # Check for sample images
    sample_dir = Path("data/sample_receipts")
    sample_images = list(sample_dir.glob("*.jpg")) + list(sample_dir.glob("*.png"))
    
    if not sample_images:
        print("⚠️  No sample images found in data/sample_receipts/")
        print("\nPlease add some receipt images to test with.")
        print("\nExample usage once you have images:")
        print("  processor.process_single_image('receipt.jpg')")
        print("  processor.process_multiple_images(['part1.jpg', 'part2.jpg'])")
        return
    
    print(f"Found {len(sample_images)} sample image(s)\n")
    
    # Demo 1: Single image processing
    print("="*60)
    print("Demo 1: Single Image Processing")
    print("="*60 + "\n")
    
    test_image = str(sample_images[0])
    print(f"Processing: {Path(test_image).name}\n")
    
    result = processor.process_single_image(
        test_image,
        preprocess=True,
        extract_metadata=True
    )
    
    print(f"Status: {result['status']}")
    print(f"Lines detected: {result.get('lines_detected', 0)}")
    print(f"Processing time: {result.get('processing_time_ms', 0)}ms")
    print(f"Average confidence: {result.get('average_confidence', 0):.1%}\n")
    
    if result.get('metadata'):
        print("Extracted Metadata:")
        for key, value in result['metadata'].items():
            print(f"  {key}: {value}")
        print()
    
    print("Text Preview (first 10 lines):")
    print("-" * 60)
    for i, line in enumerate(result.get('lines', []), 1):  # Remove [:10]
        conf = line.get('confidence', 0)
        text = line.get('text', '')
        print(f"{i:2d}. [{conf:.1%}] {text}")
    
    # Demo 2: Multiple images (if available)
    if len(sample_images) >= 2:
        print("\n" + "="*60)
        print("Demo 2: Multiple Image Processing with Stitching")
        print("="*60 + "\n")
        
        test_images = [str(img) for img in sample_images[:2]]
        print(f"Processing {len(test_images)} images:")
        for img in test_images:
            print(f"  - {Path(img).name}")
        print()
        
        result = processor.process_multiple_images(
            test_images,
            stitch=True,
            preprocess=True,
            extract_metadata=True
        )
        
        print(f"Status: {result['status']}")
        print(f"Total lines detected: {result.get('lines_detected', 0)}")
        print(f"Processing time: {result.get('processing_time_ms', 0)}ms\n")
        
        if result.get('stitching'):
            print(f"Stitching method: {result['stitching'].get('method_used', 'N/A')}")
    
    # Demo 3: Quick text extraction
    print("\n" + "="*60)
    print("Demo 3: Quick Text Extraction")
    print("="*60 + "\n")
    
    text_lines = processor.quick_text_extract(test_image)
    print(f"Extracted {len(text_lines)} lines of text:\n")
    for line in text_lines:  # Remove [:5]
        print(f"  {line}")
    if len(text_lines) > 5:
        print(f"  ... and {len(text_lines) - 5} more lines")
    
    print("\n" + "="*60)
    print("Pipeline Demo Complete!")
    print("="*60 + "\n")
    
    print("Next steps:")
    print("1. Test with your own receipt images")
    print("2. Experiment with preprocessing options")
    print("3. Try stitching multiple receipt parts")
    print("4. Review Week 1 progress and move to Week 2\n")


if __name__ == "__main__":
    main()