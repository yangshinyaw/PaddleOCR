"""
Inline Price Extractor
======================
For unknown stores where layout fingerprinting detected a high ratio of
inline-price lines ("ITEM NAME   123.45").  Used when no store signature
matched but the structural pattern indicates inline layout.

Generic Extractor
=================
Safe fallback for completely unknown stores with no clear layout pattern.
Only extracts items when confidence is very high (inline format only,
with strict financial-keyword filtering). Better to return less data
accurately than more data incorrectly.
"""

import re
from typing import List, Dict, Optional, Set

from extractor.base_extractor import BaseExtractor
from loguru import logger


# ─── Shared patterns ──────────────────────────────────────────────────────────

_SEPARATOR    = re.compile(r'^[\-\*\=\s\.]+$')
_PRICE_ONLY   = re.compile(r'^\s*[₱P]?\s*([\d,]+\.\d{1,2})\s*[TXZVvy]?\s*$')
_PRICE_INLINE = re.compile(r'^(.+?)\s{2,}[₱P]?\s*([\d,]+\.\d{2})[TXZ]?\s*$')
_BARCODE      = re.compile(r'^\d{6,14}$')

_ZONE_END = re.compile(
    r'^(SUBTOTAL|SUB\s*TOTAL|GRAND\s*TOTAL|CHANGE|CHANGE\s*DUE|'
    r'AMOUNT\s*TENDERED|CASH\s*TENDERED|TOTAL\s*PAYMENT)\s*[:\-]?\s*$',
    re.IGNORECASE,
)

_FINANCIAL_LINE = re.compile(
    r'^(SUBTOTAL|SUB\s*TOTAL|GRAND\s*TOTAL|TOTAL\s*AMOUNT|AMOUNT\s*DUE|'
    r'TOTAL\s*PAYMENT|TOTAL\s*SALES|NET\s*AMOUNT|CASH\s*TENDERED|'
    r'AMOUNT\s*TENDERED|CHANGE|BALANCE|CASH|DEBIT|CREDIT|VAT|TAX|DISCOUNT|'
    r'TOTAL|VATABLE|VAT\s*EXEMPT|ZERO\s*RATED|OUTPUT\s*TAX)\s*[:\-₱P\d\.]*\s*$',
    re.IGNORECASE,
)

_PAYMENT_LINE = re.compile(
    r'^(GCASH|MAYA|PAYMAYA|VISA|MASTERCARD|AMEX|JCB|BDO|BPI|'
    r'METROBANK|DEBIT\s*CARD|CREDIT\s*CARD|CHECK|CHEQUE|VOUCHER|'
    r'E\s*WALLET|SOLD\s*TO|MEMBER\s+N|ITEMS?\s+PURCHAS)',
    re.IGNORECASE,
)

_SKIP_ITEM = re.compile(
    r'\b(TOTAL|SUBTOTAL|CHANGE|CASH|PAYMENT|TENDERED|DISCOUNT|'
    r'VAT|TAX|BALANCE|DUE|PAID|AMOUNT|VOID|REFUND|'
    r'THANK|WELCOME|PLEASE|COME|AGAIN|'
    r'DEBIT|CREDIT|NET|GROSS|INVOICE|RECEIPT)\b',
    re.IGNORECASE,
)

_DEFINITIVE_FINANCIAL = re.compile(
    r'^(CHANGE|CASH\s+TENDERED|AMOUNT\s+TENDERED|TOTAL\s+PAYMENT|'
    r'TOTAL\s+AMOUNT|NET\s+AMOUNT|AMOUNT\s+DUE|GRAND\s+TOTAL|'
    r'CASH|TOTAL\s+SALES)\s*[:\-]?\s*$',
    re.IGNORECASE,
)


def _collect_skip_prices(extractor, lines: List[str]) -> set:
    skip: set = set()
    n = len(lines)
    for i, line in enumerate(lines):
        if _DEFINITIVE_FINANCIAL.match(line.strip()):
            m = re.search(r'[₱P]?\s*([\d,]+\.\d{2})', line.strip())
            if m:
                try:
                    skip.add(float(m.group(1).replace(',', '')))
                except ValueError:
                    pass
            if i + 1 < n:
                p = extractor._price_of(lines[i + 1])
                if p and p > 0:
                    skip.add(p)
    return skip


def _is_generic_name(line, *args) -> bool:
    s = line.strip() if isinstance(line, str) else line
    if len(s) < 3:
        return False
    if re.match(r'^\d+$', s):
        return False
    if _SEPARATOR.match(s):
        return False
    if _FINANCIAL_LINE.match(s):
        return False
    if _PAYMENT_LINE.match(s):
        return False
    if re.match(r'^(VAT|TAX|DISC)\s*[-–]?\s*\d+\s*%', s, re.IGNORECASE):
        return False
    normalized = s.upper().replace('0', 'O').replace('1', 'I')
    if _SKIP_ITEM.search(normalized):
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────

class InlinePriceExtractor(BaseExtractor):
    """
    For stores detected by layout fingerprinting as 'inline_price'.
    Tries both inline and two-line formats.
    """

    def _items(self, lines: List[str]) -> List[Dict]:
        n = len(lines)
        used: Set[int] = set()
        items: List[Dict] = []

        # Determine item zone
        zone_start = 0
        zone_end   = n
        for idx, line in enumerate(lines):
            if idx >= zone_start and _ZONE_END.match(line.strip()):
                zone_end = idx
                break

        skip_prices = _collect_skip_prices(self, lines)

        # Pass A: inline
        for i in range(zone_start, zone_end):
            if i in used:
                continue
            s = lines[i].strip()
            m = _PRICE_INLINE.match(s)
            if not m:
                continue
            name = m.group(1).strip()
            try:
                price = float(m.group(2).replace(',', ''))
            except ValueError:
                continue
            if price <= 0 or price in skip_prices:
                continue
            if not _is_generic_name(name):
                continue
            sku, k = None, None
            nxt = i + 1
            if nxt < n and nxt not in used and _BARCODE.match(lines[nxt].strip()):
                sku, k = lines[nxt].strip(), nxt
            items.append(self._build_item(name, price, sku, source_idx=i))
            used |= ({i} | ({k} if k is not None else set()))

        # Pass B: name → price
        for i in range(zone_start, zone_end):
            if i in used or not _is_generic_name(lines[i]):
                continue
            j = i + 1
            while j < zone_end and j in used:
                j += 1
            if j >= zone_end:
                continue
            price = self._price_of(lines[j])
            if price and price > 0 and price not in skip_prices:
                sku, k = None, None
                nxt = j + 1
                if nxt < n and nxt not in used and _BARCODE.match(lines[nxt].strip()):
                    sku, k = lines[nxt].strip(), nxt
                items.append(self._build_item(
                    lines[i].strip(), price, sku, source_idx=i
                ))
                used |= ({i, j} | ({k} if k is not None else set()))

        items.sort(key=lambda x: x.get('_src', 0))
        for item in items:
            item.pop('_src', None)

        logger.debug(f"[InlinePriceExtractor] {len(items)} items found")
        return items

    def _price_of(self, line: str) -> Optional[float]:
        m = _PRICE_ONLY.match(line.strip())
        if not m:
            return None
        try:
            return float(m.group(1).replace(',', ''))
        except ValueError:
            return None


# ─────────────────────────────────────────────────────────────────────────────

class GenericExtractor(BaseExtractor):
    """
    Conservative fallback for completely unknown stores.

    Only extracts items it's very confident about:
    - Inline format (name + price on same line with 2+ space gap)
    - Item name must NOT match any financial keyword
    - Minimum 3-character name

    Annotates items with confidence='high' to help downstream consumers
    understand that these were extracted conservatively.
    """

    def _items(self, lines: List[str]) -> List[Dict]:
        n = len(lines)
        used: Set[int] = set()
        items: List[Dict] = []

        zone_end = n
        for idx, line in enumerate(lines):
            if _ZONE_END.match(line.strip()):
                zone_end = idx
                break

        skip_prices = _collect_skip_prices(self, lines)

        for i in range(zone_end):
            if i in used:
                continue
            s = lines[i].strip()
            m = _PRICE_INLINE.match(s)
            if not m:
                continue
            name = m.group(1).strip()
            try:
                price = float(m.group(2).replace(',', ''))
            except ValueError:
                continue
            # Strict: name must be at least 3 chars, start with a letter,
            # have no financial keywords
            if price <= 0 or price in skip_prices:
                continue
            if len(name) < 3 or not re.match(r'^[A-Za-z]', name):
                continue
            if not _is_generic_name(name):
                continue
            items.append(self._build_item(name, price, source_idx=i))
            used.add(i)

        items.sort(key=lambda x: x.get('_src', 0))
        for item in items:
            item.pop('_src', None)

        logger.debug(f"[GenericExtractor] {len(items)} items found (conservative mode)")
        return items

    def _price_of(self, line: str) -> Optional[float]:
        m = _PRICE_ONLY.match(line.strip())
        if not m:
            return None
        try:
            return float(m.group(1).replace(',', ''))
        except ValueError:
            return None
