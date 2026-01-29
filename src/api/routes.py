"""
API Routes - All API endpoints
Handles file uploads, OCR processing, and responses
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List
import shutil
from pathlib import Path
import uuid

from api.models import OCRResponse, MetadataResponse, BatchOCRResponse
from receipt_processor import ReceiptProcessor
from loguru import logger

# Create router
router = APIRouter()

# Initialize OCR processor
processor = ReceiptProcessor()

# Upload directory
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Allowed extensions and max file size
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


# ==================== UTILITY FUNCTIONS ====================

def validate_file(file: UploadFile):
    """Validate uploaded file"""
    if not file.filename:
        raise HTTPException(400, detail="No filename provided")
    
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            detail=f"Invalid file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )


def save_upload(file: UploadFile) -> Path:
    """Save uploaded file and return path"""
    ext = Path(file.filename).suffix.lower()
    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = UPLOAD_DIR / unique_name
    
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    return file_path


# ==================== API ENDPOINTS ====================

@router.post("/ocr/scan", response_model=OCRResponse, tags=["OCR"])
async def scan_receipt(
    file: UploadFile = File(..., description="Receipt image"),
    preprocess: bool = Form(True, description="Apply grayscale preprocessing")
):
    """
    **Scan a single receipt image**
    
    Upload a receipt image and extract text using OCR.
    
    **Parameters:**
    - `file`: Receipt image file (JPG, PNG, PDF)
    - `preprocess`: Apply preprocessing (default: True)
    
    **Returns:**
    - Extracted text with confidence scores
    - Individual text lines with bounding boxes
    - Processing time
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/v1/ocr/scan \\
      -F "file=@receipt.jpg" \\
      -F "preprocess=true"
    ```
    """
    file_path = None
    try:
        # Validate
        validate_file(file)
        
        # Save file
        file_path = save_upload(file)
        logger.info(f"Processing: {file.filename}")
        
        # Process
        result = processor.process_single_image(
            str(file_path),
            preprocess=preprocess,
            extract_metadata=False
        )
        
        # Return response
        return OCRResponse(
            status="success",
            filename=file.filename,
            text=result['text'],
            confidence=result['average_confidence'],
            lines_detected=result['lines_detected'],
            lines=[
                {
                    'text': line['text'],
                    'confidence': line['confidence'],
                    'bbox': line['bbox']
                }
                for line in result['lines']
            ],
            processing_time_ms=result['processing_time_ms']
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing {file.filename}: {e}")
        raise HTTPException(500, str(e))
    finally:
        # Cleanup
        if file_path and file_path.exists():
            file_path.unlink()


@router.post("/ocr/scan-with-metadata", response_model=MetadataResponse, tags=["OCR"])
async def scan_with_metadata(
    file: UploadFile = File(..., description="Receipt image"),
    preprocess: bool = Form(True, description="Apply preprocessing")
):
    """
    **Scan receipt and extract metadata**
    
    Extract text + metadata (merchant, date, total) from receipt.
    
    **Parameters:**
    - `file`: Receipt image
    - `preprocess`: Apply preprocessing (default: True)
    
    **Returns:**
    - Extracted text
    - Merchant name, date, total amount
    - Confidence scores
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/v1/ocr/scan-with-metadata \\
      -F "file=@receipt.jpg"
    ```
    """
    file_path = None
    try:
        validate_file(file)
        file_path = save_upload(file)
        logger.info(f"Processing with metadata: {file.filename}")
        
        result = processor.process_single_image(
            str(file_path),
            preprocess=preprocess,
            extract_metadata=True
        )
        
        return MetadataResponse(
            status="success",
            filename=file.filename,
            text=result['text'],
            confidence=result['average_confidence'],
            lines_detected=result['lines_detected'],
            merchant_name=result.get('merchant_name'),
            date=result.get('date'),
            total=result.get('total'),
            items_count=result.get('items_count', 0),
            processing_time_ms=result['processing_time_ms']
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(500, str(e))
    finally:
        if file_path and file_path.exists():
            file_path.unlink()


@router.post("/ocr/scan-multiple", response_model=OCRResponse, tags=["OCR"])
async def scan_multiple(
    files: List[UploadFile] = File(..., description="Multiple receipt images"),
    stitch: bool = Form(True, description="Stitch images together"),
    preprocess: bool = Form(True, description="Apply preprocessing")
):
    """
    **Scan multiple receipt images (for split receipts)**
    
    Upload multiple images of the same receipt and combine them.
    
    **Parameters:**
    - `files`: List of receipt images (2-10 images)
    - `stitch`: Stitch images together (default: True)
    - `preprocess`: Apply preprocessing (default: True)
    
    **Returns:**
    - Combined extracted text
    - Stitching method used
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/v1/ocr/scan-multiple \\
      -F "files=@receipt_part1.jpg" \\
      -F "files=@receipt_part2.jpg"
    ```
    """
    file_paths = []
    try:
        # Validate
        if len(files) < 2:
            raise HTTPException(400, "Upload at least 2 images")
        if len(files) > 10:
            raise HTTPException(400, "Maximum 10 images")
        
        for file in files:
            validate_file(file)
        
        # Save all files
        for file in files:
            file_path = save_upload(file)
            file_paths.append(str(file_path))
        
        logger.info(f"Processing {len(files)} images")
        
        # Process
        result = processor.process_multiple_images(
            file_paths,
            stitch=stitch,
            preprocess=preprocess,
            extract_metadata=False
        )
        
        return OCRResponse(
            status="success",
            filename=f"{len(files)} images",
            text=result['text'],
            confidence=result['average_confidence'],
            lines_detected=result['lines_detected'],
            lines=[
                {
                    'text': line['text'],
                    'confidence': line['confidence'],
                    'bbox': line['bbox']
                }
                for line in result['lines']
            ],
            processing_time_ms=result['processing_time_ms'],
            stitching_method=result.get('stitching_method')
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(500, str(e))
    finally:
        # Cleanup all files
        for path in file_paths:
            Path(path).unlink(missing_ok=True)


@router.post("/ocr/batch", response_model=BatchOCRResponse, tags=["OCR"])
async def batch_scan(
    files: List[UploadFile] = File(..., description="Multiple separate receipts"),
    preprocess: bool = Form(True, description="Apply preprocessing")
):
    """
    **Batch process multiple separate receipts**
    
    Process multiple different receipts in one request.
    
    **Parameters:**
    - `files`: List of separate receipt images (1-20 images)
    - `preprocess`: Apply preprocessing (default: True)
    
    **Returns:**
    - Array of results, one per image
    - Success/failure count
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/v1/ocr/batch \\
      -F "files=@receipt1.jpg" \\
      -F "files=@receipt2.jpg" \\
      -F "files=@receipt3.jpg"
    ```
    """
    try:
        if len(files) < 1:
            raise HTTPException(400, "Upload at least 1 image")
        if len(files) > 20:
            raise HTTPException(400, "Maximum 20 images")
        
        results = []
        total_time = 0
        
        for file in files:
            file_path = None
            try:
                validate_file(file)
                file_path = save_upload(file)
                
                # Process
                result = processor.process_single_image(
                    str(file_path),
                    preprocess=preprocess,
                    extract_metadata=True
                )
                
                results.append({
                    'filename': file.filename,
                    'status': 'success',
                    'text': result['text'],
                    'confidence': result['average_confidence'],
                    'lines_detected': result['lines_detected'],
                    'merchant_name': result.get('merchant_name'),
                    'total': result.get('total'),
                    'processing_time_ms': result['processing_time_ms']
                })
                
                total_time += result['processing_time_ms']
            
            except Exception as e:
                results.append({
                    'filename': file.filename,
                    'status': 'error',
                    'error': str(e)
                })
            
            finally:
                if file_path and file_path.exists():
                    file_path.unlink()
        
        successful = sum(1 for r in results if r['status'] == 'success')
        failed = sum(1 for r in results if r['status'] == 'error')
        
        return BatchOCRResponse(
            status="success",
            total_images=len(files),
            successful=successful,
            failed=failed,
            results=results,
            total_processing_time_ms=total_time
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch error: {e}")
        raise HTTPException(500, str(e))