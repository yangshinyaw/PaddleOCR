"""
Tests for OCR Engine
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_engine import OCREngine
import cv2
import numpy as np


@pytest.fixture
def ocr_engine():
    """Create OCR engine instance for testing"""
    return OCREngine()


@pytest.fixture
def sample_image(tmp_path):
    """Create a simple test image with text"""
    # Create a white image
    img = np.ones((200, 400, 3), dtype=np.uint8) * 255
    
    # Add some text
    cv2.putText(img, "RECEIPT TEST", (50, 50), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    cv2.putText(img, "Total: $25.00", (50, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    
    # Save
    img_path = tmp_path / "test_receipt.jpg"
    cv2.imwrite(str(img_path), img)
    
    return str(img_path)


def test_ocr_engine_initialization(ocr_engine):
    """Test that OCR engine initializes properly"""
    assert ocr_engine is not None
    assert ocr_engine.ocr is not None
    assert ocr_engine.config is not None


def test_extract_text_basic(ocr_engine, sample_image):
    """Test basic text extraction"""
    result = ocr_engine.extract_text(sample_image)
    
    assert result['status'] == 'success' or result['status'] == 'no_text_found'
    assert 'lines_detected' in result
    assert 'processing_time_ms' in result


def test_extract_text_with_confidence(ocr_engine, sample_image):
    """Test text extraction with confidence scores"""
    result = ocr_engine.extract_text(sample_image, return_confidence=True)
    
    if result['status'] == 'success':
        assert len(result['lines']) > 0
        for line in result['lines']:
            assert 'text' in line
            assert 'confidence' in line
            assert 0 <= line['confidence'] <= 1


def test_extract_text_with_positions(ocr_engine, sample_image):
    """Test text extraction with position data"""
    result = ocr_engine.extract_text(sample_image, return_positions=True)
    
    if result['status'] == 'success' and len(result['lines']) > 0:
        for line in result['lines']:
            assert 'position' in line
            assert 'top' in line['position']
            assert 'left' in line['position']


def test_validate_image(ocr_engine, sample_image, tmp_path):
    """Test image validation"""
    # Valid image
    is_valid, msg = ocr_engine.validate_image(sample_image)
    assert is_valid is True
    
    # Invalid image (doesn't exist)
    is_valid, msg = ocr_engine.validate_image("nonexistent.jpg")
    assert is_valid is False
    assert "not found" in msg.lower()


def test_get_text_only(ocr_engine, sample_image):
    """Test simple text extraction"""
    text_lines = ocr_engine.get_text_only(sample_image)
    
    assert isinstance(text_lines, list)
    # May or may not detect text in simple test image


def test_batch_extract(ocr_engine, tmp_path):
    """Test batch processing"""
    # Create multiple test images
    images = []
    for i in range(3):
        img = np.ones((100, 200, 3), dtype=np.uint8) * 255
        cv2.putText(img, f"Image {i}", (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
        
        img_path = tmp_path / f"test_{i}.jpg"
        cv2.imwrite(str(img_path), img)
        images.append(str(img_path))
    
    results = ocr_engine.batch_extract(images)
    
    assert len(results) == 3
    for result in results:
        assert 'status' in result


def test_invalid_image_path(ocr_engine):
    """Test handling of invalid image path"""
    with pytest.raises(FileNotFoundError):
        ocr_engine.extract_text("this_does_not_exist.jpg")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])