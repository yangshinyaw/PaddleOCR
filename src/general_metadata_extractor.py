"""
General Metadata Extractor for Philippine Receipts
===================================================
Version 3.0 — Multi-store architecture

What changed from v2
--------------------
v2 was a single 1500-line class that handled Mercury Drug perfectly but
contained significant Mercury Drug-specific logic that silently degraded
accuracy for SM, Puregold, Jollibee, and unknown stores.

v3 uses a three-component architecture:

  1. ReceiptClassifier  — determines receipt type from store signatures
                          OR structural layout fingerprinting (for unknown stores)

  2. ExtractorFactory   — returns the right extractor strategy for each type:
                            pharmacy_column  → PharmacyColumnExtractor
                            supermarket      → SupermarketExtractor
                            fast_food        → FastFoodExtractor
                            department_store → DepartmentStoreExtractor
                            inline_price     → InlinePriceExtractor
                            generic          → GenericExtractor (safe fallback)

  3. ExtractionValidator — post-extraction sanity checks shared across all types

Key benefits
------------
- Mercury Drug logic stays in PharmacyColumnExtractor: can't bleed into SM
- New store? Add a signature to ReceiptClassifier + a new Extractor subclass
- Unknown stores get layout-fingerprinted → handled by InlinePriceExtractor
  or GenericExtractor, which are conservative but correct
- receipt_type + extraction_confidence included in every response so callers
  know how confident the system is and which path ran

Backwards compatibility
-----------------------
The public API is identical to v2:
    extractor = GeneralMetadataExtractor()
    result    = extractor.extract(text_lines)
The result dict gains two new keys: receipt_type, extraction_confidence.
"""

from typing import List, Dict, Optional

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from receipt_classifier import ReceiptClassifier
from extractor import ExtractorFactory


class ExtractionValidator:
    """
    Post-extraction sanity checks applied AFTER any extractor runs.
    These are layout-agnostic: they use numeric evidence only.
    """

    def validate(
        self,
        result: Dict,
        raw_lines: List[str],
        stated_count: Optional[int],
    ) -> Dict:
        result = self._add_warnings(result)
        return result

    def _add_warnings(self, result: Dict) -> Dict:
        """Add a warning flag if item sum is wildly inconsistent with total."""
        items = result.get("items", [])
        total_str = result.get("total_amount")
        if not items or not total_str:
            return result

        try:
            total_float = float(total_str.replace("₱", "").replace(",", ""))
        except ValueError:
            return result

        item_sum = sum(
            i.get("price", 0) * (i.get("qty") or 1) for i in items
        )

        # Allow up to 50% over total (discounts can reduce the final bill
        # significantly on senior/PWD/BP-discount pharmacy receipts)
        if item_sum > total_float * 1.5:
            result["extraction_warning"] = "item_sum_exceeds_total"
            logger.warning(
                f"[Validator] item_sum={item_sum:.2f} >> total={total_float:.2f}"
            )

        return result


class GeneralMetadataExtractor:
    """
    Public entry point.  Orchestrates:
      classify → extract → validate

    Usage
    -----
        extractor = GeneralMetadataExtractor()
        result    = extractor.extract(text_lines)

    Result keys
    -----------
    store_name, invoice_number, date, time, total_amount, vat_amount,
    tin, item_count, stated_item_count, has_vat, items,
    receipt_type, receipt_type_confidence, extraction_confidence,
    extraction_warning (optional)
    """

    def __init__(self):
        self._classifier = ReceiptClassifier()
        self._factory    = ExtractorFactory()
        self._validator  = ExtractionValidator()

    def extract(self, text_lines: List[str]) -> Dict:
        """
        Extract structured metadata from raw OCR text lines.

        Parameters
        ----------
        text_lines : list of str
            Raw OCR output, one string per detected text line.

        Returns
        -------
        dict
        """
        if not text_lines:
            return self._empty()

        cleaned = [l.strip() for l in text_lines if l.strip()]
        if not cleaned:
            return self._empty()

        # 1. Classify
        receipt_type, type_confidence = self._classifier.classify(cleaned)
        logger.info(
            f"[GeneralMetadataExtractor] receipt_type={receipt_type!r} "
            f"confidence={type_confidence}"
        )

        # 2. Extract with the right strategy
        extractor = self._factory.get_extractor(receipt_type)
        result    = extractor.extract(cleaned)

        # 3. Validate
        stated_count = result.get("stated_item_count")
        result = self._validator.validate(result, cleaned, stated_count)

        # 4. Annotate with classification metadata
        result["receipt_type"]            = receipt_type
        result["receipt_type_confidence"] = type_confidence

        logger.info(
            f"[GeneralMetadataExtractor] done — "
            f"store={result.get('store_name')!r} "
            f"items={result.get('item_count', 0)} "
            f"extraction_confidence={result.get('extraction_confidence', 0):.2f}"
        )
        return result

    @staticmethod
    def _empty() -> Dict:
        return {
            "store_name":              None,
            "invoice_number":          None,
            "date":                    None,
            "time":                    None,
            "total_amount":            None,
            "vat_amount":              None,
            "tin":                     None,
            "item_count":              0,
            "stated_item_count":       None,
            "has_vat":                 False,
            "items":                   [],
            "receipt_type":            "generic",
            "receipt_type_confidence": "low",
            "extraction_confidence":   0.0,
        }


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    # ── Test 1: Mercury Drug ──────────────────────────────────────────────────
    mercury_lines = [
        "MERCURY DRUG - RIZAL BANANGONAN EM COMPLEX",
        "EM Complex, Manila East Road,",
        "Brgy.Pantok,Binangonan, Rizal",
        "VAT REG TIN : 000-388-474-00778",
        "MOBILE/VIBER NO : 0908813-2818",
        "TOSHIBA4900 41CRD20R003 01070",
        "PA99S/S",
        "1220.00T",
        "NIDO5+PDR MLK2kg",
        "480036140523",
        "90.00T",
        "GREEN COF MX219",
        "TOTAL",
        "1310.00",
        "AMOUNT TENDERED",
        "CASH",
        "2000.00",
        "CHANGE",
        "690.00",
        "** 2 item(s) **",
        "VAT - 12%  140.36",
        "TXN#110855 11-13-25 02:15P EJ",
        "INVOICE#110703137533",
    ]

    e = GeneralMetadataExtractor()
    r = e.extract(mercury_lines)
    print("\n=== Mercury Drug ===")
    print(json.dumps(r, indent=2, ensure_ascii=False))

    assert r["receipt_type"] == "pharmacy_column", f"Expected pharmacy_column, got {r['receipt_type']}"
    assert r["store_name"] == "MERCURY DRUG - RIZAL BANANGONAN EM COMPLEX"
    assert r["invoice_number"] == "110703137533"
    assert r["date"] == "11-13-25"
    assert r["total_amount"] == "₱1,310.00"
    assert r["vat_amount"] == "₱140.36"
    assert r["tin"] == "000-388-474-00778"
    assert len(r["items"]) >= 1
    nido = next((x for x in r["items"] if "NIDO" in x["name"]), None)
    assert nido is not None, "NIDO item not found"
    assert nido["price"] == 1220.0
    print("✅ Mercury Drug assertions passed")

    # ── Test 2: Fast food (simple) ────────────────────────────────────────────
    ff_lines = [
        "JOLLIBEE",
        "SM MALL OF ASIA",
        "ORDER # 4521",
        "DINE IN",
        "1 CHICKENJOY 1PC   79.00",
        "1 JOLLY SPAGHETTI   65.00",
        "FRIES REGULAR   55.00",
        "SUBTOTAL",
        "199.00",
        "TOTAL",
        "199.00",
        "CASH  200.00",
        "CHANGE  1.00",
    ]

    r2 = e.extract(ff_lines)
    print("\n=== Jollibee ===")
    print(json.dumps(r2, indent=2, ensure_ascii=False))
    assert r2["receipt_type"] == "fast_food", f"Expected fast_food, got {r2['receipt_type']}"
    assert r2["store_name"] == "JOLLIBEE"
    print("✅ Fast food assertions passed")

    print("\n✅ ALL SELF-TESTS PASSED")