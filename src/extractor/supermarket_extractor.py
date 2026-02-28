"""
Supermarket Extractor
=====================
Handles SM Supermarket, Puregold, S&R, Shopwise, Robinsons Supermarket,
Walter Mart, Landers, and similar Philippine grocery chains.

Layout characteristics
----------------------
- Items appear as inline "NAME   PRICE" (single line, 2+ space gap)
  OR as two lines: "NAME" then "PRICE" on the next line.
- Loyalty card section, VAT breakdown, and footer appear AFTER CHANGE/TOTAL.
- "** N item(s) **" count line is a reliable ground-truth for validation.
- Currency header "PHP" appears before the item list on some SM receipts.
- Item list ends at SUBTOTAL / GRAND TOTAL / CHANGE DUE.

Passes
------
  A  : inline "ITEM NAME   123.45"
  B  : two-line "ITEM NAME" → "123.45"
  C  : three-line "ITEM NAME" → barcode → "123.45"  (some SM formats)
"""

import re
from typing import List, Dict, Optional, Set, Tuple

from extractor.base_extractor import BaseExtractor
from loguru import logger


# ─── Patterns ─────────────────────────────────────────────────────────────────

_SEPARATOR = re.compile(r'^[\-\*\=\s\.]+$|^\*\*.*\*\*$')
_PRICE_ONLY = re.compile(r'^\s*[₱P]?\s*([\d,]+\.\d{1,2})\s*[TXZVvy]?\s*$')
_PRICE_INLINE = re.compile(r'^(.+?)\s{2,}[₱P]?\s*([\d,]+\.\d{2})[TXZ]?\s*$')
_BARCODE = re.compile(r'^\d{6,14}$')

_ZONE_START = re.compile(
    r'^PH[PO]\s*$',  # SM currency header — "PHP" or "PHO" (OCR misread of P→O)
    re.IGNORECASE
)
_ZONE_END = re.compile(
    r'^(SUBTOTAL|SUB\s*TOTAL|GRAND\s*TOTAL|CHANGE|CHANGE\s*DUE|'
    r'AMOUNT\s*TENDERED|CASH\s*TENDERED|TOTAL\s*PAYMENT)\s*[:\-]?\s*$',
    re.IGNORECASE,
)

_SKIP_ITEM = re.compile(
    r'\b(TOTAL|SUBTOTAL|CHANGE|CASH|CARD|PAYMENT|TENDERED|DISCOUNT|LESS|'
    r'VAT|TAX|BALANCE|DUE|PAID|AMOUNT|VOID|REFUND|TIN|DATE|TIME|CASHIER|'
    r'THANK|WELCOME|PLEASE|COME|AGAIN|SAVE|SENIOR|PWD|MEMBER|POINTS|LOYALTY|'
    r'DEBIT|CREDIT|NET|GROSS|INVOICE|SOLD|ADDRESS|VATAble|Exempt|Zero|Rated|'
    r'RECEIPT|YOUR|THIS|MERCHANDISE|CONDITION|SALAMAT|MARAMING|items?)\b',
    re.IGNORECASE,
)

_FINANCIAL_LINE = re.compile(
    r'^(SUBTOTAL|SUB\s*TOTAL|GRAND\s*TOTAL|TOTAL\s*AMOUNT|AMOUNT\s*DUE|'
    r'TOTAL\s*PAYMENT|TOTAL\s*SALES|NET\s*AMOUNT|CASH\s*TENDERED|'
    r'AMOUNT\s*TENDERED|CHANGE|BALANCE|CASH|DEBIT|CREDIT|VAT|TAX|'
    r'DISCOUNT|TOTAL|VATABLE|VAT\s*EXEMPT|ZERO\s*RATED)\s*[:\-₱P\d\.]*\s*$',
    re.IGNORECASE,
)

_PAYMENT_LINE = re.compile(
    r'^(GCASH|MAYA|PAYMAYA|VISA|MASTERCARD|AMEX|JCB|'
    r'BDO|BPI|METROBANK|DEBIT\s*CARD|CREDIT\s*CARD|'
    r'CHECK|CHEQUE|VOUCHER|E\s*WALLET|MEMBER\s+N|ITEMS?\s+PURCHAS|'
    r'SOLDTO|SOLD\s*TO|NAME\s*:\s*$|TIN\s*NO|ADDRESS)',
    re.IGNORECASE,
)

_ITEM_COUNT_LINE = re.compile(
    r'\*+\s*(\d+)\s*item(?:s|\(s\))?\s*\**',
    re.IGNORECASE,
)

_ITEMS_PURCHASED = re.compile(
    r'ITEMS?\s+PURCHAS(?:ED|EO|E)\s*[:#]?\s*(\d+)',
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    t = text.upper()
    return t.replace('0', 'O').replace('1', 'I').replace('|', 'I')


class SupermarketExtractor(BaseExtractor):
    """
    Extractor for inline-price supermarket receipts.
    """

    def _items(self, lines: List[str]) -> List[Dict]:
        n = len(lines)
        used: Set[int] = set()
        items: List[Dict] = []

        # ── Item zone ─────────────────────────────────────────────────────────
        zone_start = 0
        zone_end   = n

        for idx, line in enumerate(lines):
            s = line.strip()
            if zone_start == 0 and _ZONE_START.match(s):
                zone_start = idx + 1
                used.add(idx)
                continue
            if idx >= zone_start and _ZONE_END.match(s):
                zone_end = idx
                break

        skip_prices = self._collect_skip_prices(lines)

        # ── Pass A: inline "NAME   PRICE" ────────────────────────────────────
        _INLINE_QTY = re.compile(r'^(.+?)\s{2,}(\d{1,4}\s*[@xX×]\s*[\d,]+\.\d{2})\s*$')
        for i in range(zone_start, zone_end):
            if i in used:
                continue
            s = lines[i].strip()

            # Sub-case: inline qty — "NAME   2 @ 45.00" (qty IS the inline value)
            m_qty = _INLINE_QTY.match(s)
            if m_qty:
                name = m_qty.group(1).strip()
                if self._is_name(name, n, i):
                    qty_parsed, unit_parsed = self._parse_qty_line(m_qty.group(2).strip())
                    if qty_parsed is not None:
                        j = self._next_free(i + 1, n, used)
                        if j is not None:
                            price = self._price_of(lines[j])
                            if price and price > 0 and price not in skip_prices:
                                sku, k = self._maybe_barcode(j + 1, n, used, lines)
                                items.append(self._build_item(name, price, sku,
                                             qty=qty_parsed, unit_price=unit_parsed, source_idx=i))
                                used |= ({i, j} | ({k} if k is not None else set()))
                                continue

            # Standard inline: "NAME   PRICE"
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
            if not self._is_name(name, n, i):
                continue
            # Check if next line is a qty line
            qty, unit_price = None, None
            q_idx = None
            j_next = self._next_free(i + 1, n, used)
            if j_next is not None:
                _qty, _unit = self._parse_qty_line(lines[j_next])
                if _qty is not None:
                    qty, unit_price, q_idx = _qty, _unit, j_next
            sku, k = self._maybe_barcode(
                q_idx + 1 if q_idx is not None else i + 1, n, used, lines
            )
            items.append(self._build_item(name, price, sku,
                                          qty=qty, unit_price=unit_price, source_idx=i))
            used |= ({i}
                     | ({q_idx} if q_idx is not None else set())
                     | ({k} if k is not None else set()))

        # ── Pass A2: name → qty_line → price (Wilkins format) ────────────────
        # "WILKINS 500ML"   ← name
        # "2 @ 45.00"       ← qty × unit_price
        # "90.00"           ← total price
        for i in range(zone_start, zone_end):
            if i in used or not self._is_name(lines[i], n, i):
                continue
            j = self._next_free(i + 1, n, used)
            if j is None:
                continue
            qty, unit_price = self._parse_qty_line(lines[j])
            if qty is None:
                continue
            k = self._next_free(j + 1, n, used)
            if k is None:
                continue
            price = self._price_of(lines[k])
            if price and price > 0 and price not in skip_prices:
                sku, m_idx = self._maybe_barcode(k + 1, n, used, lines)
                items.append(self._build_item(lines[i].strip(), price, sku,
                                              qty=qty, unit_price=unit_price, source_idx=i))
                used |= ({i, j, k} | ({m_idx} if m_idx is not None else set()))

        # ── Pass B: name → price → [optional qty line] ──────────────────────
        # SM Supermarket format:
        #   "+Yakult 5s"   ← name
        #   "100.00"       ← price
        #   "2X50.00"      ← qty × unit_price (AFTER price, not before)
        for i in range(zone_start, zone_end):
            if i in used or not self._is_name(lines[i], n, i):
                continue
            j = i + 1
            while j < zone_end and j in used:
                j += 1
            if j >= zone_end:
                continue
            price = self._price_of(lines[j])
            if price and price > 0 and price not in skip_prices:
                # Check for qty line immediately AFTER the price (SM format)
                qty, unit_price, q_idx = None, None, None
                k_next = self._next_free(j + 1, n, used)
                if k_next is not None and k_next < zone_end:
                    _qty, _unit = self._parse_qty_line(lines[k_next])
                    if _qty is not None:
                        qty, unit_price, q_idx = _qty, _unit, k_next
                sku, k = self._maybe_barcode(
                    q_idx + 1 if q_idx is not None else j + 1, n, used, lines
                )
                items.append(self._build_item(
                    lines[i].strip(), price, sku,
                    qty=qty, unit_price=unit_price, source_idx=i
                ))
                used |= ({i, j}
                         | ({q_idx} if q_idx is not None else set())
                         | ({k} if k is not None else set()))

        # ── Pass C: name → barcode → price ───────────────────────────────────
        for i in range(zone_start, zone_end):
            if i in used or not self._is_name(lines[i], n, i):
                continue
            j = i + 1
            if j >= n or j in used or not _BARCODE.match(lines[j].strip()):
                continue
            k = j + 1
            if k >= n or k in used:
                continue
            price = self._price_of(lines[k])
            if price and price > 0 and price not in skip_prices:
                items.append(self._build_item(
                    lines[i].strip(), price, lines[j].strip(), source_idx=i
                ))
                used |= {i, j, k}

        # Sort and clean
        items.sort(key=lambda x: x.get('_src', 0))
        for item in items:
            item.pop('_src', None)

        # Validate against stated count
        stated = self._stated_item_count(lines)
        if stated and len(items) > stated:
            items = self._cap_to_stated(items, stated)

        logger.debug(f"[SupermarketExtractor] {len(items)} items found")
        return items

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _collect_skip_prices(self, lines: List[str]) -> set:
        skip: set = set()
        _DEFINITIVE = re.compile(
            r'^(CHANGE|CASH\s+TENDERED|AMOUNT\s+TENDERED|TOTAL\s+PAYMENT|'
            r'TOTAL\s+AMOUNT|NET\s+AMOUNT|AMOUNT\s+DUE|GRAND\s+TOTAL|'
            r'CASH|TOTAL\s+SALES)\s*[:\-]?\s*$',
            re.IGNORECASE,
        )
        n = len(lines)
        for i, line in enumerate(lines):
            s = line.strip()
            if _DEFINITIVE.match(s):
                m = re.search(r'[₱P]?\s*([\d,]+\.\d{2})', s)
                if m:
                    try:
                        skip.add(float(m.group(1).replace(',', '')))
                    except ValueError:
                        pass
                if i + 1 < n:
                    p = self._price_of(lines[i + 1])
                    if p and p > 0:
                        skip.add(p)
        return skip

    def _is_name(self, line, total_lines: int = 0, line_idx: int = 0) -> bool:
        s = line.strip() if isinstance(line, str) else line
        if len(s) < 2:
            return False
        if self._price_of(s) is not None:
            return False
        if _BARCODE.match(s):
            return False
        if _SEPARATOR.match(s):
            return False
        if re.match(r'^\d+$', s):
            return False
        if _FINANCIAL_LINE.match(s):
            return False
        if _PAYMENT_LINE.match(s):
            return False
        if re.match(r'^(VAT|TAX|DISC)\s*[-–]?\s*\d+\s*%', s, re.IGNORECASE):
            return False
        normalized = _normalize(s)
        if _SKIP_ITEM.search(normalized):
            return False
        return True

    def _price_of(self, line: str) -> Optional[float]:
        m = _PRICE_ONLY.match(line.strip())
        if not m:
            return None
        try:
            return float(m.group(1).replace(',', ''))
        except ValueError:
            return None

    def _next_free(self, start: int, n: int, used: set) -> Optional[int]:
        for idx in range(start, n):
            if idx not in used:
                return idx
        return None

    def _parse_qty_line(self, line: str):
        """Parse '2 @ 45.00' or '3x36.00' → (qty, unit_price) or (None, None)."""
        m = re.match(r'^(\d{1,4})\s*[@xX×]\s*([\d,]+\.\d{2})\s*$', line.strip())
        if m:
            try:
                return int(m.group(1)), float(m.group(2).replace(',', ''))
            except ValueError:
                pass
        return None, None

    def _maybe_barcode(self, start, n, used, lines):
        for k in range(start, n):
            if k not in used:
                if _BARCODE.match(lines[k].strip()):
                    return lines[k].strip(), k
                break
        return None, None

    def _stated_item_count(self, lines: List[str]) -> Optional[int]:
        # Only use "** N item(s) **" format — this is unique product line count.
        # Do NOT use "ITEMS PURCHASED: N" — on SM receipts this is the total
        # quantity sold (sum of all qtys), not the number of unique product lines.
        # Using it would incorrectly cap item extraction to the wrong number.
        for line in lines:
            m = _ITEM_COUNT_LINE.search(line)
            if m:
                try:
                    return int(m.group(1))
                except (ValueError, IndexError):
                    pass
        return None

    def _cap_to_stated(self, items: List[Dict], stated: int) -> List[Dict]:
        def priority(item):
            score = 0
            if not item.get('sku'):   score += 5
            if len(item['name']) <= 4: score += 3
            return score
        return sorted(items, key=priority, reverse=True)[:stated]