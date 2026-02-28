"""
API Models — Request and Response schemas
Using Pydantic for automatic validation and documentation

Changes from v1
---------------
MetadataResponse.metadata now includes:
  receipt_type            - which store layout was detected
  receipt_type_confidence - 'high' | 'medium' | 'low'
  extraction_confidence   - 0–1 numeric score
  extraction_warning      - optional flag if something looks off

HealthResponse now has a `version` field.
BatchOCRItem now has a `receipt_type` field.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


# ─── OCR Models ───────────────────────────────────────────────────────────────

class OCRLine(BaseModel):
    """Individual text line from OCR."""
    text: str       = Field(..., description="Extracted text")
    confidence: float = Field(..., description="Confidence score (0-1)", ge=0, le=1)
    bbox: List[List[int]] = Field(..., description="Bounding box coordinates")


class OCRResponse(BaseModel):
    """Standard OCR response — text extraction without metadata."""
    status: str           = Field("success",  description="Response status")
    filename: str         = Field(...,         description="Processed filename")
    text: str             = Field(...,         description="Full extracted text (line-by-line)")
    formatted_text: Optional[str] = Field(None, description="Formatted text (row-by-row)")
    confidence: float     = Field(...,         description="Average confidence score", ge=0, le=1)
    lines_detected: int   = Field(...,         description="Number of text lines detected")
    rows_detected: Optional[int] = Field(None, description="Number of rows detected")
    lines: List[OCRLine]  = Field(...,         description="Individual text lines")
    rows: Optional[List[Dict]] = Field(None,   description="Structured row data")
    processing_time_ms: int = Field(...,       description="Processing time in milliseconds")
    stitching_method: Optional[str] = Field(None, description="Stitching method used")


class MetadataResponse(BaseModel):
    """OCR response with extracted receipt metadata."""
    status: str           = Field("success",  description="Response status")
    filename: str         = Field(...,         description="Processed filename")
    text: str             = Field(...,         description="Full extracted text")
    formatted_text: Optional[str] = Field(None, description="Formatted text (row-by-row)")
    confidence: float     = Field(...,         description="Average confidence score", ge=0, le=1)
    lines_detected: int   = Field(...,         description="Number of text lines detected")
    rows_detected: Optional[int] = Field(None, description="Number of rows detected")

    # Individual lines
    lines: Optional[List[OCRLine]] = Field(None, description="Individual text lines with confidence")
    rows:  Optional[List[Dict]]    = Field(None, description="Structured row data")

    # Extracted metadata (from GeneralMetadataExtractor v3)
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Extracted receipt metadata. "
            "Includes: store_name, invoice_number, date, time, total_amount, "
            "vat_amount, tin, item_count, has_vat, items, "
            "receipt_type, receipt_type_confidence, extraction_confidence."
        ),
    )

    processing_time_ms: int = Field(..., description="Processing time in milliseconds")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "filename": "mercury_drug_receipt.jpg",
                "text": "MERCURY DRUG\n...",
                "confidence": 0.963,
                "lines_detected": 65,
                "metadata": {
                    "store_name": "MERCURY DRUG - RIZAL BANANGONAN EM COMPLEX",
                    "invoice_number": "110703137533",
                    "date": "11-13-25",
                    "time": "02:15P",
                    "total_amount": "₱1,310.00",
                    "vat_amount": "₱140.36",
                    "tin": "000-388-474-00778",
                    "item_count": 2,
                    "has_vat": True,
                    "receipt_type": "pharmacy_column",
                    "receipt_type_confidence": "high",
                    "extraction_confidence": 0.9,
                    "items": [
                        {
                            "name": "NIDO5+PDR MLK2kg",
                            "price": 1220.0,
                            "qty": 1,
                            "unit_price": None,
                            "sku": "480036140523",
                        }
                    ],
                },
                "processing_time_ms": 1250,
            }
        }


class BatchOCRItem(BaseModel):
    """Single item in batch OCR results."""
    filename: str
    status: str
    text: Optional[str]           = None
    confidence: Optional[float]   = None
    lines_detected: Optional[int] = None
    merchant_name: Optional[str]  = None
    total: Optional[str]          = None
    receipt_type: Optional[str]   = None   # NEW: which layout was detected
    processing_time_ms: Optional[int] = None
    error: Optional[str]          = None


class BatchOCRResponse(BaseModel):
    """Batch processing response."""
    status: str          = Field("success", description="Overall status")
    total_images: int    = Field(..., description="Total images processed")
    successful: int      = Field(..., description="Successfully processed")
    failed: int          = Field(..., description="Failed to process")
    results: List[BatchOCRItem] = Field(..., description="Individual results")
    total_processing_time_ms: int = Field(..., description="Total processing time")


# ─── Health & Error Models ────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Health check response — used by AWS ALB target health checks."""
    status: str  = Field("healthy",           description="Health status")
    service: str = Field("receipt-ocr-api",   description="Service name")
    version: str = Field("3.0.0",             description="API version")


class ErrorResponse(BaseModel):
    """Error response."""
    status: str           = Field("error", description="Response status")
    error: str            = Field(...,     description="Error type")
    message: str          = Field(...,     description="Error message")
    detail: Optional[str] = Field(None,    description="Additional details")