"""
API Routes - All API endpoints
FIXED: Properly integrates with GeneralMetadataExtractor
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
        
        # Process (no metadata extraction for basic scan)
        result = processor.process_single_image(
            str(file_path),
            preprocess=preprocess,
            extract_metadata=False
        )
        
        # Return response
        return OCRResponse(
            status="success",
            filename=file.filename,
            text=result.get('text', ''),
            formatted_text=result.get('formatted_text'),
            confidence=result.get('average_confidence', 0),
            lines_detected=result.get('lines_detected', 0),
            rows_detected=result.get('rows_detected'),
            lines=[
                {
                    'text': line.get('text', ''),
                    'confidence': line.get('confidence', 0),
                    'bbox': line.get('bbox', [])
                }
                for line in result.get('lines', [])
            ],
            rows=result.get('rows'),
            processing_time_ms=result.get('processing_time_ms', 0)
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
    
    Extract text + metadata (store, invoice, date, items) from receipt.
    Uses GeneralMetadataExtractor - works with ANY Philippines store.
    
    **Parameters:**
    - `file`: Receipt image
    - `preprocess`: Apply preprocessing (default: True)
    
    **Returns:**
    - Extracted text (raw and formatted)
    - All lines with confidence scores
    - Store name, invoice #, date, items with SKU & price
    - Processing details
    
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
        
        # Process with metadata extraction
        result = processor.process_single_image(
            str(file_path),
            preprocess=preprocess,
            extract_metadata=True  # This triggers GeneralMetadataExtractor
        )
        
        # Extract the metadata dict (created by GeneralMetadataExtractor)
        extracted_metadata = result.get('metadata', {})
        
        # Build proper metadata response
        metadata_response = {
            'store_name': extracted_metadata.get('store_name'),
            'invoice_number': extracted_metadata.get('invoice_number'),
            'date': extracted_metadata.get('date'),
            'time': extracted_metadata.get('time'),
            'total_amount': extracted_metadata.get('total_amount'),
            'vat_amount': extracted_metadata.get('vat_amount'),
            'tin': extracted_metadata.get('tin'),
            'item_count': extracted_metadata.get('item_count', 0),
            'has_vat': extracted_metadata.get('has_vat', False),
            'items': extracted_metadata.get('items', [])
        }
        
        logger.info(f"✅ Metadata extracted: Store={metadata_response['store_name']}, "
                   f"Invoice={metadata_response['invoice_number']}, "
                   f"Items={metadata_response['item_count']}")
        
        return MetadataResponse(
            status="success",
            filename=file.filename,
            text=result.get('text', ''),
            formatted_text=result.get('formatted_text'),
            confidence=result.get('average_confidence', 0),
            lines_detected=result.get('lines_detected', 0),
            rows_detected=result.get('rows_detected'),
            lines=[
                {
                    'text': line.get('text', ''),
                    'confidence': line.get('confidence', 0),
                    'bbox': line.get('bbox', [])
                }
                for line in result.get('lines', [])
            ],
            rows=result.get('rows'),
            metadata=metadata_response,
            processing_time_ms=result.get('processing_time_ms', 0)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}")
        logger.exception("Full traceback:")  # Add full traceback for debugging
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
            text=result.get('text', ''),
            formatted_text=result.get('formatted_text'),
            confidence=result.get('average_confidence', 0),
            lines_detected=result.get('lines_detected', 0),
            rows_detected=result.get('rows_detected'),
            lines=[
                {
                    'text': line.get('text', ''),
                    'confidence': line.get('confidence', 0),
                    'bbox': line.get('bbox', [])
                }
                for line in result.get('lines', [])
            ],
            rows=result.get('rows'),
            processing_time_ms=result.get('processing_time_ms', 0),
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
                
                # Process with metadata
                result = processor.process_single_image(
                    str(file_path),
                    preprocess=preprocess,
                    extract_metadata=True
                )
                
                # Extract metadata
                metadata = result.get('metadata', {})
                
                results.append({
                    'filename': file.filename,
                    'status': 'success',
                    'text': result.get('text', ''),
                    'confidence': result.get('average_confidence', 0),
                    'lines_detected': result.get('lines_detected', 0),
                    'merchant_name': metadata.get('store_name'),  # Fixed key
                    'total': metadata.get('total_amount'),         # Fixed key
                    'processing_time_ms': result.get('processing_time_ms', 0)
                })
                
                total_time += result.get('processing_time_ms', 0)
            
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