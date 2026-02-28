"""
Fast Food Extractor
===================
Handles Jollibee, McDonald's, Chowking, Mang Inasal, Greenwich, Red Ribbon,
Burger King, Pizza Hut, KFC, Subway, Wendy's, Popeyes, Shakey's.

Layout characteristics
----------------------
Fast food receipts vary by chain but share common traits:

  - Combo meals listed as a header + add-ons indented beneath
  - Items often appear as: "ITEM NAME   QTY   PRICE"
    or as: "ITEM NAME   PRICE" (qty implied as 1)
  - Some chains have "1 CHICKENJOY   69.00" (qty prefix)
  - Order number, table number, cashier, dine-in/take-out header lines
  - Short receipts — typically 5–25 items

Passes
------
  A  : inline "QTY ITEM NAME   PRICE" or "ITEM NAME   PRICE"
  B  : two-line "ITEM NAME" then "PRICE"
"""

import re
from typing import List, Dict, Optional, Set

from extractor.base_extractor import BaseExtractor
from loguru import logger


_SEPARATOR   = re.compile(r'^[\-\*\=\s\.]+$')
_PRICE_ONLY  = re.compile(r'^\s*[₱P]?\s*([\d,]+\.\d{1,2})\s*$')
_PRICE_INLINE = re.compile(r'^(.+?)\s{2,}[₱P]?\s*([\d,]+\.\d{2})\s*$')

# "1 CHICKENJOY   69.00"  or  "3 PEACH MANGO PIE  69.00"
_QTY_PREFIX = re.compile(r'^(\d{1,2})\s+(.+?)\s{2,}[₱P]?\s*([\d,]+\.\d{2})\s*$')

_SKIP = re.compile(
    r'\b(TOTAL|SUBTOTAL|CHANGE|CASH|PAYMENT|TENDERED|DISCOUNT|'
    r'VAT|TAX|BALANCE|DUE|PAID|AMOUNT|VOID|REFUND|TIN|DATE|TIME|'
    r'THANK|WELCOME|CASHIER|ORDER|TABLE|DINE|TAKE|DRIVE|'
    r'DEBIT|CREDIT|INVOICE|RECEIPT)\b',
    re.IGNORECASE,
)

_ZONE_END = re.compile(
    r'^(SUBTOTAL|SUB\s*TOTAL|GRAND\s*TOTAL|CHANGE|TOTAL)\s*[:\-]?\s*$',
    re.IGNORECASE,
)

_ORDER_HEADER = re.compile(
    r'^(ORDER\s*#|TABLE\s*#|CASHIER\s*#|DINE\s*IN|TAKE\s*OUT|DRIVE\s*THRU)',
    re.IGNORECASE,
)


class FastFoodExtractor(BaseExtractor):
    """
    Extractor for fast food receipts.
    """

    def _items(self, lines: List[str]) -> List[Dict]:
        n = len(lines)
        used: Set[int] = set()
        items: List[Dict] = []

        # ── Zone: skip header (order/table/cashier lines), end at TOTAL ───────
        zone_start = 0
        zone_end   = n

        # Find first item-like line after the header block
        for idx, line in enumerate(lines):
            s = line.strip()
            if _ORDER_HEADER.match(s):
                used.add(idx)
                zone_start = idx + 1
            if idx >= zone_start and _ZONE_END.match(s):
                zone_end = idx
                break

        skip_prices = self._collect_skip_prices(lines)

        # ── Pass A: inline with optional qty prefix ───────────────────────────
        for i in range(zone_start, zone_end):
            if i in used:
                continue
            s = lines[i].strip()

            # Try qty-prefix first: "2 PEACH MANGO PIE   69.00"
            mq = _QTY_PREFIX.match(s)
            if mq:
                try:
                    qty   = int(mq.group(1))
                    name  = mq.group(2).strip()
                    price = float(mq.group(3).replace(',', ''))
                except ValueError:
                    mq = None
                else:
                    if price > 0 and price not in skip_prices and self._is_name(name):
                        items.append(self._build_item(name, price, qty=qty, source_idx=i))
                        used.add(i)
                        continue

            # Plain inline: "CHICKENJOY   69.00"
            m = _PRICE_INLINE.match(s)
            if m:
                name = m.group(1).strip()
                try:
                    price = float(m.group(2).replace(',', ''))
                except ValueError:
                    continue
                if price > 0 and price not in skip_prices and self._is_name(name):
                    items.append(self._build_item(name, price, source_idx=i))
                    used.add(i)

        # ── Pass B: two-line name → price ────────────────────────────────────
        for i in range(zone_start, zone_end):
            if i in used or not self._is_name(lines[i]):
                continue
            j = i + 1
            while j < zone_end and j in used:
                j += 1
            if j >= zone_end:
                continue
            price = self._price_of(lines[j])
            if price and price > 0 and price not in skip_prices:
                items.append(self._build_item(lines[i].strip(), price, source_idx=i))
                used |= {i, j}

        items.sort(key=lambda x: x.get('_src', 0))
        for item in items:
            item.pop('_src', None)

        logger.debug(f"[FastFoodExtractor] {len(items)} items found")
        return items

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _collect_skip_prices(self, lines: List[str]) -> set:
        skip: set = set()
        _DEF = re.compile(
            r'^(CHANGE|CASH\s+TENDERED|AMOUNT\s+TENDERED|TOTAL\s+PAYMENT|'
            r'TOTAL\s+AMOUNT|NET\s+AMOUNT|AMOUNT\s+DUE|GRAND\s+TOTAL|CASH)\s*[:\-]?\s*$',
            re.IGNORECASE,
        )
        n = len(lines)
        for i, line in enumerate(lines):
            if _DEF.match(line.strip()):
                if i + 1 < n:
                    p = self._price_of(lines[i + 1])
                    if p:
                        skip.add(p)
        return skip

    def _is_name(self, line, *args) -> bool:
        s = line.strip() if isinstance(line, str) else line
        if len(s) < 2:
            return False
        if self._price_of(s) is not None:
            return False
        if re.match(r'^\d+$', s):
            return False
        if _SEPARATOR.match(s):
            return False
        if _ORDER_HEADER.match(s):
            return False
        normalized = s.upper().replace('0', 'O').replace('1', 'I')
        if _SKIP.search(normalized):
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
