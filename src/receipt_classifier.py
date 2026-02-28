"""
Receipt Classifier for Philippine Receipts
==========================================
Classifies receipt type BEFORE extraction so the right extractor is used.

Two classification strategies work in tandem:

  1. Signature matching  — looks for known store names, TINs, and layout markers
                           that unambiguously identify a chain (Mercury Drug, SM, etc.)

  2. Layout fingerprinting — when the store is unknown, detects the receipt's
                             structural pattern from line-type ratios.
                             A receipt with many standalone price-only lines is a
                             pharmacy / column-split layout even if you've never
                             seen that store before.

Receipt types returned
──────────────────────
  'pharmacy_column'   Mercury Drug, Rose Pharmacy, Generika, Watsons, South Star Drug
                      Two-column layout: OCR reads price column before name column.

  'supermarket'       SM, Puregold, S&R, Shopwise, Robinsons Supermarket
                      Inline or name-then-price format, loyalty-card footer.

  'fast_food'         Jollibee, McDonald's, Chowking, Mang Inasal, Greenwich,
                      Burger King, Pizza Hut, KFC, Subway, Wendy's, Popeyes
                      Order-based layout with table/order number.

  'department_store'  SM Department, National Bookstore, Landmark, Rustan's
                      Retail receipt with item code + description + price.

  'inline_price'      Any unknown store where most items are on single lines
                      ("ITEM NAME   123.45").  Generic but layout-detected.

  'generic'           Safe fallback — only high-confidence patterns used.
"""

import re
from typing import List, Tuple
from loguru import logger


# ─── Store signatures ─────────────────────────────────────────────────────────

_SIGNATURES: dict[str, dict] = {

    "pharmacy_column": {
        # Known chains — any single match → classified
        "chain_patterns": [
            re.compile(r'MERCURY\s+DRUG', re.IGNORECASE),
            re.compile(r'ROSE\s+PHARMACY', re.IGNORECASE),
            re.compile(r'GENERIKA', re.IGNORECASE),
            re.compile(r'WATSONS', re.IGNORECASE),
            re.compile(r'SOUTH\s+STAR\s+DRUG', re.IGNORECASE),
            re.compile(r'THE\s+GENERICS\s+PHARMACY', re.IGNORECASE),
            re.compile(r'FARMACIA', re.IGNORECASE),
            re.compile(r'BOTICA', re.IGNORECASE),
        ],
        # Layout markers — any single match → classified
        "layout_patterns": [
            re.compile(r'^PA\s*#?\s*\d+', re.IGNORECASE),        # PA#99 S/S (Mercury Drug Rx mode)
            re.compile(r'LESS\s*:?\s*BP\s+DISC', re.IGNORECASE), # blood-pressure discount
            re.compile(r'LESS\s*:?\s*SC\s+DISC', re.IGNORECASE), # senior-citizen discount
            re.compile(r'Phillogix', re.IGNORECASE),              # Mercury Drug POS vendor
            re.compile(r'VAT\s*REG\s*TIN\s*:\s*000-388', re.IGNORECASE),  # Mercury Drug TIN prefix
        ],
    },

    "supermarket": {
        "chain_patterns": [
            re.compile(r'SM\s+SUPERMARKET', re.IGNORECASE),
            re.compile(r'SM\s+SAVEMORE', re.IGNORECASE),
            re.compile(r'PUREGOLD', re.IGNORECASE),
            re.compile(r'S&R\s+MEMBERSHIP', re.IGNORECASE),
            re.compile(r'SHOPWISE', re.IGNORECASE),
            re.compile(r'ROBINSONS\s+SUPERMARKET', re.IGNORECASE),
            re.compile(r'WALTER\s+MART', re.IGNORECASE),
            re.compile(r'PRICE\s+SMART', re.IGNORECASE),
            re.compile(r'LANDERS\s+SUPERSTORE', re.IGNORECASE),
        ],
        "layout_patterns": [
            re.compile(r'^\*{1,3}\s*\d+\s*item', re.IGNORECASE),          # ** 6 item(s) **
            re.compile(r'^ITEMS?\s+PURCHAS', re.IGNORECASE),                # ITEMS PURCHASED : 8
            re.compile(r'^PHP\s*$', re.IGNORECASE),                         # SM currency header
            re.compile(r'Vincor\s+Nixdorf', re.IGNORECASE),                 # SM POS vendor
            re.compile(r'MEMBER\s+N[AO](?:NE|ME|)', re.IGNORECASE),        # MEMBER NANE:
        ],
    },

    "fast_food": {
        "chain_patterns": [
            re.compile(r'JOLLIBEE', re.IGNORECASE),
            re.compile(r"MCDONALD'?S", re.IGNORECASE),
            re.compile(r'CHOWKING', re.IGNORECASE),
            re.compile(r'MANG\s+INASAL', re.IGNORECASE),
            re.compile(r'GREENWICH', re.IGNORECASE),
            re.compile(r'RED\s+RIBBON', re.IGNORECASE),
            re.compile(r'BURGER\s+KING', re.IGNORECASE),
            re.compile(r'PIZZA\s+HUT', re.IGNORECASE),
            re.compile(r'\bKFC\b', re.IGNORECASE),
            re.compile(r'\bSUBWAY\b', re.IGNORECASE),
            re.compile(r"WENDY'?S", re.IGNORECASE),
            re.compile(r'POPEYES', re.IGNORECASE),
            re.compile(r'SHAKEYS', re.IGNORECASE),
            re.compile(r"KENNY\s+ROGER'?S", re.IGNORECASE),
        ],
        "layout_patterns": [
            re.compile(r'^ORDER\s*#\s*\d', re.IGNORECASE),
            re.compile(r'^TABLE\s*#?\s*\d', re.IGNORECASE),
            re.compile(r'^DINE\s*[-\s]?IN\b', re.IGNORECASE),
            re.compile(r'^TAKE\s*[-\s]?OUT\b', re.IGNORECASE),
            re.compile(r'^DRIVE\s*[-\s]?THRU\b', re.IGNORECASE),
            re.compile(r'^CASHIER\s*[:#]?\s*\d', re.IGNORECASE),
        ],
    },

    "department_store": {
        "chain_patterns": [
            re.compile(r'SM\s+DEPARTMENT', re.IGNORECASE),
            re.compile(r'NATIONAL\s+BOOKSTORE', re.IGNORECASE),
            re.compile(r'\bLANDMARK\b', re.IGNORECASE),
            re.compile(r"RUSTAN'?S", re.IGNORECASE),
            re.compile(r'THE\s+LANDMARK', re.IGNORECASE),
            re.compile(r'METRO\s+GAISANO', re.IGNORECASE),
            re.compile(r'GAISANO\s+MALL', re.IGNORECASE),
            re.compile(r'\bROBINSONS\s+DEPARTMENT\b', re.IGNORECASE),
            re.compile(r'KULTURA', re.IGNORECASE),
        ],
        "layout_patterns": [
            re.compile(r'^ITEM\s+CODE\s*:', re.IGNORECASE),
            re.compile(r'^DESCRIPTION\s+QTY\s+PRICE', re.IGNORECASE),
        ],
    },
}


# ─── Layout fingerprinting thresholds ────────────────────────────────────────

# Ratio of standalone-price-only lines → suggests column-split layout
_STANDALONE_PRICE_RATIO_THRESHOLD = 0.12

# Ratio of inline "text   price" lines → suggests inline layout
_INLINE_PRICE_RATIO_THRESHOLD = 0.18

_PRICE_ONLY = re.compile(r'^\s*[₱P]?\s*[\d,]+\.\d{2}\s*[TXZVvy]?\s*$')
_PRICE_INLINE = re.compile(r'^.+\s{2,}[₱P]?\s*[\d,]+\.\d{2}\s*[TXZ]?\s*$')


class ReceiptClassifier:
    """
    Classify a receipt from its raw OCR text lines.

    Usage
    -----
    classifier = ReceiptClassifier()
    receipt_type, confidence = classifier.classify(lines)
    # receipt_type: str  e.g. 'pharmacy_column'
    # confidence:   str  'high' | 'medium' | 'low'
    """

    def classify(self, lines: List[str]) -> Tuple[str, str]:
        """
        Classify receipt type from OCR lines.

        Returns
        -------
        (receipt_type, confidence)
            receipt_type : one of the keys listed in module docstring
            confidence   : 'high' (signature match), 'medium' (layout),
                           'low' (generic fallback)
        """
        if not lines:
            return "generic", "low"

        text_block = "\n".join(lines)

        # ── Pass 1: chain name / TIN / POS vendor signature ──────────────────
        for rtype, sig in _SIGNATURES.items():
            for pat in sig["chain_patterns"]:
                if pat.search(text_block):
                    logger.debug(f"[Classifier] {rtype} (chain match: {pat.pattern})")
                    return rtype, "high"

        # ── Pass 2: layout markers (PA#, PHP header, ORDER#, etc.) ───────────
        for rtype, sig in _SIGNATURES.items():
            for pat in sig.get("layout_patterns", []):
                for line in lines:
                    if pat.search(line.strip()):
                        logger.debug(f"[Classifier] {rtype} (layout marker: {pat.pattern})")
                        return rtype, "high"

        # ── Pass 3: structural fingerprinting (unknown stores) ────────────────
        layout_type = self._fingerprint_layout(lines)
        if layout_type != "generic":
            logger.debug(f"[Classifier] {layout_type} (layout fingerprint)")
            return layout_type, "medium"

        logger.debug("[Classifier] generic (no match)")
        return "generic", "low"

    def _fingerprint_layout(self, lines: List[str]) -> str:
        """
        Classify by structural ratios when no store name is recognised.

        Heuristic rationale
        -------------------
        Pharmacy/column-split receipts (Mercury Drug style) have a high ratio
        of standalone price lines because the two OCR columns produce:
            "1220.00T"          ← standalone price
            "NIDO5+PDR MLK2kg"  ← item name on the next line
        so roughly every item creates one standalone price line.

        Pure inline-price receipts (department / general retail) have a high
        ratio of lines that contain both a text fragment and a price on the
        same line ("POLO SHIRT   599.00").

        If neither ratio is high enough we fall back to 'generic'.
        """
        if not lines:
            return "generic"

        total = len(lines)
        standalone_prices = sum(1 for l in lines if _PRICE_ONLY.match(l.strip()))
        inline_prices = sum(
            1 for l in lines
            if _PRICE_INLINE.match(l.strip()) and not _PRICE_ONLY.match(l.strip())
        )

        standalone_ratio = standalone_prices / total
        inline_ratio = inline_prices / total

        logger.debug(
            f"[Classifier] fingerprint: total={total} "
            f"standalone={standalone_prices}({standalone_ratio:.2f}) "
            f"inline={inline_prices}({inline_ratio:.2f})"
        )

        if standalone_ratio >= _STANDALONE_PRICE_RATIO_THRESHOLD:
            return "pharmacy_column"
        if inline_ratio >= _INLINE_PRICE_RATIO_THRESHOLD:
            return "inline_price"
        return "generic"
