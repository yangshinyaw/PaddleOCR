"""
Extractor Factory
=================
Routes to the correct extractor strategy based on receipt_type.

Usage
-----
    factory   = ExtractorFactory()
    extractor = factory.get_extractor("pharmacy_column")
    metadata  = extractor.extract(lines)
"""

from extractor.base_extractor import BaseExtractor
from extractor.pharmacy_extractor import PharmacyColumnExtractor
from extractor.supermarket_extractor import SupermarketExtractor
from extractor.fast_food_extractor import FastFoodExtractor
from extractor.department_store_extractor import DepartmentStoreExtractor
from extractor.inline_and_generic_extractors import InlinePriceExtractor, GenericExtractor

from loguru import logger


class ExtractorFactory:
    """
    Returns the appropriate extractor for a given receipt type.

    If the receipt type is unknown or not supported, falls back to
    GenericExtractor (safe, conservative extraction).
    """

    _EXTRACTORS: dict[str, BaseExtractor] = {}   # lazy-initialized singletons

    # ── Mapping: receipt_type → extractor class ───────────────────────────────
    _CLASSES = {
        "pharmacy_column":  PharmacyColumnExtractor,
        "supermarket":      SupermarketExtractor,
        "fast_food":        FastFoodExtractor,
        "department_store": DepartmentStoreExtractor,
        "inline_price":     InlinePriceExtractor,
        "generic":          GenericExtractor,
    }

    def get_extractor(self, receipt_type: str) -> BaseExtractor:
        """
        Return a (cached) extractor instance for the given receipt type.

        Parameters
        ----------
        receipt_type : str
            One of: 'pharmacy_column', 'supermarket', 'fast_food',
                    'department_store', 'inline_price', 'generic'

        Returns
        -------
        BaseExtractor subclass instance
        """
        if receipt_type not in self._CLASSES:
            logger.warning(
                f"[ExtractorFactory] Unknown receipt type '{receipt_type}', "
                f"falling back to GenericExtractor"
            )
            receipt_type = "generic"

        # Lazy-initialise singleton per type
        if receipt_type not in self._EXTRACTORS:
            cls = self._CLASSES[receipt_type]
            self._EXTRACTORS[receipt_type] = cls()
            logger.debug(f"[ExtractorFactory] Initialised {cls.__name__}")

        return self._EXTRACTORS[receipt_type]

    @property
    def supported_types(self) -> list:
        """List of all supported receipt type strings."""
        return list(self._CLASSES.keys())
