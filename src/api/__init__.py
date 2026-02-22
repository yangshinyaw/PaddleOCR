"""
API Package
Contains FastAPI routes and models
"""

from api.routes import router
from api.models import (
    OCRResponse,
    MetadataResponse,
    BatchOCRResponse,
    HealthResponse,
    ErrorResponse
)

__all__ = [
    'router',
    'OCRResponse',
    'MetadataResponse',
    'BatchOCRResponse',
    'HealthResponse',
    'ErrorResponse'
]