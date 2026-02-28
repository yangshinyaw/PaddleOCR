"""
Extractor package — strategy-based metadata extractors for Philippine receipts.

Each extractor handles the item extraction logic for one receipt layout type.
All shared fields (store_name, date, time, total, VAT, TIN, invoice) live in
BaseExtractor and are identical across all store types.

Usage (via factory)
-------------------
from extractor import ExtractorFactory
factory = ExtractorFactory()
extractor = factory.get_extractor("pharmacy_column")
metadata  = extractor.extract(lines)
"""

from extractor.factory import ExtractorFactory

__all__ = ["ExtractorFactory"]
