"""
Department Store Extractor
==========================
Handles SM Department Store, National Bookstore, Landmark, Rustan's,
Gaisano Mall, Robinsons Department Store, and similar retail chains.

Layout characteristics
----------------------
- Items usually have: ITEM CODE / DESCRIPTION / QTY / PRICE
- Or inline: "ITEM DESCRIPTION   QTY   PRICE"
- Larger item count, longer item names
- May have section headers (CLOTHING, ACCESSORIES, etc.)

Passes
------
  A  : inline with trailing price ("POLO SHIRT BLUE M   1   599.00")
  B  : inline simple ("POLO SHIRT BLUE M   599.00")
  C  : two-line name → price
"""

import re
from typing import List, Dict, Optional, Set

from extractor.base_extractor import BaseExtractor
from loguru import logger


_SEPARATOR    = re.compile(r'^[\-\*\=\s\.]+$')
_PRICE_ONLY   = re.compile(r'^\s*[₱P]?\s*([\d,]+\.\d{1,2})\s*$')
_PRICE_INLINE = re.compile(r'^(.+?)\s{2,}[₱P]?\s*([\d,]+\.\d{2})\s*$')

# Retail: "ITEM DESC   2   599.00" (qty before price)
_QTY_PRICE_INLINE = re.compile(
    r'^(.+?)\s{2,}(\d{1,3})\s{1,4}[₱P]?\s*([\d,]+\.\d{2})\s*$'
)

_ZONE_END = re.compile(
    r'^(SUBTOTAL|SUB\s*TOTAL|GRAND\s*TOTAL|CHANGE|TOTAL\s*AMOUNT|'
    r'AMOUNT\s*DUE|NET\s*AMOUNT)\s*[:\-]?\s*$',
    re.IGNORECASE,
)

_SKIP_ITEM = re.compile(
    r'\b(TOTAL|SUBTOTAL|CHANGE|CASH|PAYMENT|TENDERED|DISCOUNT|'
    r'VAT|TAX|BALANCE|DUE|PAID|AMOUNT|VOID|REFUND|'
    r'THANK|WELCOME|DEBIT|CREDIT|INVOICE|RECEIPT|'
    r'SECTION|DEPARTMENT|CATEGORY)\b',
    re.IGNORECASE,
)

_DEFINITIVE_FINANCIAL = re.compile(
    r'^(CHANGE|CASH\s+TENDERED|AMOUNT\s+TENDERED|TOTAL\s+PAYMENT|'
    r'TOTAL\s+AMOUNT|NET\s+AMOUNT|AMOUNT\s+DUE|GRAND\s+TOTAL|CASH)\s*[:\-]?\s*$',
    re.IGNORECASE,
)


class DepartmentStoreExtractor(BaseExtractor):
    """
    Extractor for retail/department store receipts.
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

        skip_prices = self._collect_skip_prices(lines)

        # Pass A: "ITEM NAME   QTY   PRICE"
        for i in range(zone_end):
            if i in used:
                continue
            s = lines[i].strip()
            mq = _QTY_PRICE_INLINE.match(s)
            if mq:
                name = mq.group(1).strip()
                try:
                    qty   = int(mq.group(2))
                    price = float(mq.group(3).replace(',', ''))
                except ValueError:
                    continue
                if price > 0 and price not in skip_prices and self._is_name(name):
                    items.append(self._build_item(name, price, qty=qty, source_idx=i))
                    used.add(i)
                    continue

            # Pass B: "ITEM NAME   PRICE"
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

        # Pass C: name → price
        for i in range(zone_end):
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

        logger.debug(f"[DepartmentStoreExtractor] {len(items)} items found")
        return items

    def _collect_skip_prices(self, lines: List[str]) -> set:
        skip: set = set()
        n = len(lines)
        for i, line in enumerate(lines):
            if _DEFINITIVE_FINANCIAL.match(line.strip()):
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
        normalized = s.upper().replace('0', 'O').replace('1', 'I')
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
