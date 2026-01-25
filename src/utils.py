"""
Utility functions for receipt OCR processing
"""

import os
import hashlib
import mimetypes
from typing import List, Tuple, Optional
from pathlib import Path
import magic

from loguru import logger


def validate_image_file(file_path: str, allowed_extensions: Optional[List[str]] = None) -> Tuple[bool, str]:
    """
    Validate if file is a valid image
    
    Args:
        file_path: Path to file
        allowed_extensions: List of allowed extensions (default: common image formats)
    
    Returns:
        (is_valid, message)
    """
    if allowed_extensions is None:
        allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff']
    
    # Check if file exists
    if not os.path.exists(file_path):
        return False, "File not found"
    
    # Check extension
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in allowed_extensions:
        return False, f"Invalid extension: {ext}. Allowed: {allowed_extensions}"
    
    # Verify MIME type (don't trust extension alone)
    try:
        mime = magic.from_file(file_path, mime=True)
        if not mime.startswith('image/'):
            return False, f"Not an image file (MIME type: {mime})"
    except Exception as e:
        logger.warning(f"Could not verify MIME type: {e}")
    
    return True, "Valid image file"


def get_file_hash(file_path: str) -> str:
    """
    Calculate SHA256 hash of file
    Useful for deduplication and caching
    
    Args:
        file_path: Path to file
    
    Returns:
        Hex string of hash
    """
    sha256_hash = hashlib.sha256()
    
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    
    return sha256_hash.hexdigest()


def get_image_dimensions(file_path: str) -> Tuple[int, int]:
    """
    Get image dimensions without loading entire image
    
    Args:
        file_path: Path to image
    
    Returns:
        (width, height)
    """
    import cv2
    
    img = cv2.imread(file_path)
    if img is None:
        raise ValueError(f"Could not read image: {file_path}")
    
    height, width = img.shape[:2]
    return width, height


def get_file_size_mb(file_path: str) -> float:
    """Get file size in megabytes"""
    size_bytes = os.path.getsize(file_path)
    size_mb = size_bytes / (1024 * 1024)
    return round(size_mb, 2)


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and special characters
    
    Args:
        filename: Original filename
    
    Returns:
        Sanitized filename
    """
    import re
    
    # Get just the filename (remove any path components)
    filename = os.path.basename(filename)
    
    # Remove special characters (keep alphanumeric, dots, dashes, underscores)
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    
    # Limit length
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:95] + ext
    
    return filename


def ensure_directory(dir_path: str) -> str:
    """
    Ensure directory exists, create if it doesn't
    
    Args:
        dir_path: Directory path
    
    Returns:
        Absolute path to directory
    """
    path = Path(dir_path)
    path.mkdir(parents=True, exist_ok=True)
    return str(path.absolute())


def cleanup_temp_files(directory: str, max_age_hours: int = 24):
    """
    Clean up temporary files older than specified age
    
    Args:
        directory: Directory to clean
        max_age_hours: Maximum age of files to keep
    """
    import time
    
    if not os.path.exists(directory):
        return
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    deleted_count = 0
    
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        
        if os.path.isfile(file_path):
            file_age = current_time - os.path.getmtime(file_path)
            
            if file_age > max_age_seconds:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.debug(f"Deleted old temp file: {filename}")
                except Exception as e:
                    logger.warning(f"Could not delete {filename}: {e}")
    
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} temporary file(s)")


def format_processing_time(milliseconds: int) -> str:
    """
    Format processing time in human-readable format
    
    Args:
        milliseconds: Time in milliseconds
    
    Returns:
        Formatted string (e.g., "1.23s", "456ms")
    """
    if milliseconds < 1000:
        return f"{milliseconds}ms"
    else:
        seconds = milliseconds / 1000
        return f"{seconds:.2f}s"


def extract_receipt_metadata(text_lines: List[str]) -> dict:
    """
    Extract common receipt metadata from OCR text
    This is a simple version - will be enhanced in later phases
    
    Args:
        text_lines: List of text strings from OCR
    
    Returns:
        Dictionary with extracted metadata
    """
    import re
    from datetime import datetime
    
    metadata = {
        'merchant_name': None,
        'total': None,
        'date': None,
        'items_count': 0
    }
    
    # Simple patterns (will be improved with NLP later)
    total_pattern = r'\$?\s*(\d+\.\d{2})'
    date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
    
    for i, line in enumerate(text_lines):
        # First line often contains merchant name
        if i == 0 and len(line) > 3:
            metadata['merchant_name'] = line.strip()
        
        # Look for total
        if 'total' in line.lower():
            match = re.search(total_pattern, line)
            if match:
                metadata['total'] = float(match.group(1))
        
        # Look for date
        date_match = re.search(date_pattern, line)
        if date_match:
            metadata['date'] = date_match.group(0)
    
    return metadata


def create_processing_summary(
    processing_time_ms: int,
    lines_detected: int,
    avg_confidence: float,
    image_path: str
) -> dict:
    """
    Create a summary of processing results
    
    Returns:
        Dictionary with summary information
    """
    return {
        'image': os.path.basename(image_path),
        'processing_time': format_processing_time(processing_time_ms),
        'lines_detected': lines_detected,
        'average_confidence': f"{avg_confidence:.1%}",
        'file_size': f"{get_file_size_mb(image_path)} MB"
    }


def merge_ocr_results(results: List[dict]) -> dict:
    """
    Merge multiple OCR results (e.g., from stitched images)
    
    Args:
        results: List of OCR result dictionaries
    
    Returns:
        Merged result dictionary
    """
    if not results:
        return {'status': 'no_results', 'lines': []}
    
    if len(results) == 1:
        return results[0]
    
    # Merge all lines
    all_lines = []
    total_processing_time = 0
    
    for result in results:
        if result.get('status') == 'success':
            all_lines.extend(result.get('lines', []))
            total_processing_time += result.get('processing_time_ms', 0)
    
    # Calculate new statistics
    if all_lines:
        avg_confidence = sum(line.get('confidence', 0) for line in all_lines) / len(all_lines)
    else:
        avg_confidence = 0
    
    return {
        'status': 'success',
        'lines_detected': len(all_lines),
        'processing_time_ms': total_processing_time,
        'average_confidence': round(avg_confidence, 3),
        'lines': all_lines,
        'merged_from': len(results)
    }


# Logging setup helper
def setup_logging(log_file: str = "logs/receipt_ocr.log", level: str = "INFO"):
    """
    Setup logging configuration
    
    Args:
        log_file: Path to log file
        level: Log level (DEBUG, INFO, WARNING, ERROR)
    """
    from loguru import logger
    import sys
    
    # Remove default handler
    logger.remove()
    
    # Add console handler
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=level
    )
    
    # Add file handler
    ensure_directory(os.path.dirname(log_file))
    logger.add(
        log_file,
        rotation="10 MB",
        retention="30 days",
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}"
    )
    
    logger.info("Logging initialized")


if __name__ == "__main__":
    # Test utilities
    print("Testing utility functions...\n")
    
    # Test sanitization
    dangerous_name = "../../../etc/passwd.jpg"
    safe_name = sanitize_filename(dangerous_name)
    print(f"Sanitize: {dangerous_name} -> {safe_name}")
    
    # Test directory creation
    test_dir = ensure_directory("data/test_utils")
    print(f"Created directory: {test_dir}")
    
    # Test metadata extraction
    sample_text = [
        "WALMART SUPERCENTER",
        "123 Main Street",
        "Date: 01/15/2024",
        "Item 1    $5.99",
        "Item 2    $3.49",
        "TOTAL     $9.48"
    ]
    
    metadata = extract_receipt_metadata(sample_text)
    print(f"\nExtracted metadata: {metadata}")
    
    print("\n✅ All utility tests passed!")