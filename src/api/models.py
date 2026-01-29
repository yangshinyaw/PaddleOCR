"""
API Models - Request and Response schemas
Using Pydantic for automatic validation and documentation
"""

from pydantic import BaseModel, Field
from typing import List, Optional


# ==================== OCR Models ====================

class OCRLine(BaseModel):
    """Individual text line from OCR"""
    text: str = Field(..., description="Extracted text")
    confidence: float = Field(..., description="Confidence score (0-1)", ge=0, le=1)
    bbox: List[List[int]] = Field(..., description="Bounding box coordinates")


class OCRResponse(BaseModel):
    """Standard OCR response"""
    status: str = Field("success", description="Response status")
    filename: str = Field(..., description="Processed filename")
    text: str = Field(..., description="Full extracted text")
    confidence: float = Field(..., description="Average confidence score", ge=0, le=1)
    lines_detected: int = Field(..., description="Number of text lines detected")
    lines: List[OCRLine] = Field(..., description="Individual text lines")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    stitching_method: Optional[str] = Field(None, description="Stitching method used (if applicable)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "filename": "receipt.jpg",
                "text": "WALMART\\nReceipt #12345\\nTotal: $45.99",
                "confidence": 0.963,
                "lines_detected": 65,
                "lines": [
                    {
                        "text": "WALMART",
                        "confidence": 0.98,
                        "bbox": [[10, 20], [100, 20], [100, 50], [10, 50]]
                    }
                ],
                "processing_time_ms": 1250
            }
        }


class MetadataResponse(BaseModel):
    """OCR response with extracted metadata"""
    status: str = Field("success", description="Response status")
    filename: str = Field(..., description="Processed filename")
    text: str = Field(..., description="Full extracted text")
    confidence: float = Field(..., description="Average confidence score", ge=0, le=1)
    lines_detected: int = Field(..., description="Number of text lines detected")
    
    # Extracted metadata
    merchant_name: Optional[str] = Field(None, description="Merchant/store name")
    date: Optional[str] = Field(None, description="Receipt date")
    total: Optional[str] = Field(None, description="Total amount")
    items_count: int = Field(0, description="Number of items detected")
    
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "filename": "receipt.jpg",
                "text": "WALMART\\nDate: 01/28/2026\\nTotal: $45.99",
                "confidence": 0.963,
                "lines_detected": 65,
                "merchant_name": "WALMART",
                "date": "01/28/2026",
                "total": "$45.99",
                "items_count": 5,
                "processing_time_ms": 1350
            }
        }


class BatchOCRItem(BaseModel):
    """Single item in batch OCR results"""
    filename: str
    status: str
    text: Optional[str] = None
    confidence: Optional[float] = None
    lines_detected: Optional[int] = None
    merchant_name: Optional[str] = None
    total: Optional[str] = None
    processing_time_ms: Optional[int] = None
    error: Optional[str] = None


class BatchOCRResponse(BaseModel):
    """Batch processing response"""
    status: str = Field("success", description="Overall status")
    total_images: int = Field(..., description="Total images processed")
    successful: int = Field(..., description="Successfully processed")
    failed: int = Field(..., description="Failed to process")
    results: List[BatchOCRItem] = Field(..., description="Individual results")
    total_processing_time_ms: int = Field(..., description="Total processing time")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "total_images": 3,
                "successful": 3,
                "failed": 0,
                "results": [
                    {
                        "filename": "receipt1.jpg",
                        "status": "success",
                        "text": "WALMART...",
                        "confidence": 0.96,
                        "lines_detected": 45,
                        "merchant_name": "WALMART",
                        "total": "$25.99",
                        "processing_time_ms": 1200
                    }
                ],
                "total_processing_time_ms": 3600
            }
        }


# ==================== Health & Error Models ====================

class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field("healthy", description="Health status")
    service: str = Field("receipt-ocr-api", description="Service name")
    version: str = Field("1.0.0", description="API version")


class ErrorResponse(BaseModel):
    """Error response"""
    status: str = Field("error", description="Response status")
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "error",
                "error": "ValidationError",
                "message": "Invalid file type",
                "detail": "Only JPG, PNG, and PDF files are allowed"
            }
        }
