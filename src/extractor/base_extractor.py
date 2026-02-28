"""
Base Extractor
==============
Contains ALL shared extraction logic:
  - store_name   (first non-trivial line)
  - invoice_number
  - date
  - time
  - total_amount
  - vat_amount
  - tin

Subclasses override ONLY _items() to handle their specific layout.

This file is intentionally self-contained: all regex patterns it needs
are defined here so subclasses don't need to import from the old monolith.
"""

import re
from typing import List, Dict, Optional
from loguru import logger


# ─── Shared compiled patterns ─────────────────────────────────────────────────

_SEPARATOR = re.compile(r'^[\-\*\=\s\.]+$|^\*\*.*\*\*$')

_MONTH_NAMES = (
    r'(?:January|February|March|April|May|June|July|August|September|'
    r'October|November|December|'
    r'Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
)

_DATE_PATTERNS = [
    # ── Numeric with 4-digit year (unambiguous) ───────────────────────────────
    re.compile(r'\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})\b'),        # 02/28/2026  28-02-2026  28.02.2026
    re.compile(r'\b(\d{4}[/\-\.]\d{2}[/\-\.]\d{2})\b'),             # 2026-02-28 (ISO 8601)

    # ── Written with 4-digit year ─────────────────────────────────────────────
    re.compile(r'\b(\d{1,2}(?:st|nd|rd|th)?\s+' + _MONTH_NAMES + r'\.?,?\s+\d{4})\b', re.IGNORECASE),  # 28 Feb 2026 / 28th February, 2026
    re.compile(r'\b(' + _MONTH_NAMES + r'\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\b', re.IGNORECASE),  # Feb 28, 2026

    # ── Formal: "The 28th of February, 2026" ─────────────────────────────────
    re.compile(r'\b(The\s+\d{1,2}(?:st|nd|rd|th)?\s+of\s+' + _MONTH_NAMES + r',?\s+\d{4})\b', re.IGNORECASE),

    # ── Numeric with 2-digit year (Mercury Drug / common PH receipts) ─────────
    re.compile(r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2})\b'),             # 11-13-25  02/28/26

    # ── Written with 2-digit year ─────────────────────────────────────────────
    re.compile(r'\b(\d{1,2}\s+' + _MONTH_NAMES + r'\.?\s+\d{2})\b', re.IGNORECASE),   # 28 Feb 26
    re.compile(r'\b(' + _MONTH_NAMES + r"\.?\s+'?\d{2})\b", re.IGNORECASE),             # Feb '26

    # ── Month-year only ───────────────────────────────────────────────────────
    re.compile(r'\b(\d{2}[/\-]\d{4})\b'),                            # 02/2026
    re.compile(r'\b(' + _MONTH_NAMES + r'\.?\s+\d{4})\b', re.IGNORECASE),  # February 2026

    # ── Ordinal / casual (day + month, no year) ───────────────────────────────
    re.compile(r'\b(\d{1,2}(?:st|nd|rd|th)?\s+' + _MONTH_NAMES + r')\b', re.IGNORECASE),   # 28th February
    re.compile(r'\b(' + _MONTH_NAMES + r'\.?\s+\d{1,2}(?:st|nd|rd|th)?)\b', re.IGNORECASE), # Feb 28th

    # ── Day/Month no year — last resort, easily confused with prices ──────────
    re.compile(r'\b(\d{1,2}/\d{1,2})\b'),                            # 28/2
]

_TIME_PATTERNS = [
    re.compile(r'\b(\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM|[AP]M?)?)\\b', re.IGNORECASE),
    re.compile(r'\b(\d{1,2}:\d{2}\s*[AP]M?)\b', re.IGNORECASE),
    re.compile(r'\b(\d{1,2}:\d{2}\s*(?:AM|PM))\b', re.IGNORECASE),
]

_INVOICE_PATTERNS = [
    re.compile(r'\bSALESINVOICE\s*(\d{6,})', re.IGNORECASE),
    re.compile(r'\bINVOICE\s*#\s*([A-Z0-9]{6,})', re.IGNORECASE),  # INVOICE#10S064482477
    re.compile(r'\bINVOICE\s*#\s*(\d{4,})', re.IGNORECASE),
    re.compile(r'\bINVOICE\s*#\s*([A-Z0-9\-]{4,})', re.IGNORECASE),
    re.compile(r'\b(?:OR|SI)\s*#\s*([A-Z0-9][A-Z0-9\-]{3,})', re.IGNORECASE),
    re.compile(r'\b(?:O\.R\.|S\.I\.)\s*#?\s*:?\s*([A-Z0-9\-]{4,})', re.IGNORECASE),
    re.compile(r'\b(?:OFFICIAL RECEIPT|SALES INVOICE|RECEIPT NO\.?)\s*#?\s*:?\s*([A-Z0-9\-]{4,})', re.IGNORECASE),
    re.compile(r'\bSI\s+No\s*[:#]\s*(\d{4,})', re.IGNORECASE),
    re.compile(r'\bTXN\s*#\s*(\w{4,})', re.IGNORECASE),
    re.compile(r'\b(?:TRANSACTION|CONTROL)\s*(?:NO\.?|#)\s*:?\s*([A-Z0-9\-]{4,})', re.IGNORECASE),
]

_TOTAL_PATTERNS = [
    re.compile(r'GRAND\s+TOTAL\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'TOTAL\s+AMOUNT\s+DUE\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'AMOUNT\s+DUE\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'TOTAL\s+PAYMENT\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'TOTAL\s+SALES\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'NET\s+AMOUNT\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'NET\s+SALES\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'(?<!\w)TOTAL\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
]

_TOTAL_KW_PRIORITY = [
    re.compile(r'^GRAND\s+TOTAL\s*[:\-]?\s*$', re.IGNORECASE),
    re.compile(r'^TOTAL\s+AMOUNT\s+DUE\s*[:\-]?\s*$', re.IGNORECASE),
    re.compile(r'^TOTAL\s+AMOUNT\s*[:\-]?\s*$', re.IGNORECASE),
    re.compile(r'^TOTAL\s+SALES\s*[:\-]?\s*$', re.IGNORECASE),
    re.compile(r'^NET\s+AMOUNT\s*[:\-]?\s*$', re.IGNORECASE),
    re.compile(r'^AMOUNT\s+DUE\s*[:\-]?\s*$', re.IGNORECASE),
    re.compile(r'^TOTAL\s*[:\-]?\s*$', re.IGNORECASE),         # plain TOTAL (after discount)
    re.compile(r'^TOTAL\s+PAYMENT\s*[:\-]?\s*$', re.IGNORECASE),
    # NOTE: SUBTOTAL intentionally excluded — it's always pre-discount
]

_VAT_PATTERNS = [
    re.compile(r'(?:VAT\s*[-–]?\s*12%|12%\s*VAT|OUTPUT\s*TAX|VAT\s*AMOUNT)\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'VAT\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
]

_VAT_KW = re.compile(
    r'^(VAT\s*[-–]?\s*\d*\s*%?|VAT\s+AMOUNT|OUTPUT\s+TAX|VAT)\s*[:\-]?\s*$',
    re.IGNORECASE
)

_TIN_PATTERNS = [
    re.compile(r'(?:VAT\s+REG\s+)?TIN\s*[:\-]?\s*(\d{3}[\-\s]\d{3}[\-\s]\d{3}[\-\s\d]+)', re.IGNORECASE),
    re.compile(r'TIN\s*[:\-]?\s*(\d{9,15})', re.IGNORECASE),
]

_PRICE_ONLY = re.compile(r'^\s*[₱P]?\s*([\d,]+\.\d{1,2})\s*[TXZVvy]?\s*$')


class BaseExtractor:
    """
    Abstract base class.  Subclasses implement _items().

    Call extract(lines) → returns the full metadata dict.
    """

    # ── Public entry point ────────────────────────────────────────────────────

    def extract(self, lines: List[str]) -> Dict:
        """
        Extract all receipt metadata from raw OCR lines.

        Returns
        -------
        Dict with keys: store_name, invoice_number, date, time,
        total_amount, vat_amount, tin, item_count, has_vat, items,
        extraction_confidence
        """
        if not lines:
            return self._empty()

        cleaned = [l.strip() for l in lines if l.strip()]
        if not cleaned:
            return self._empty()

        store_name     = self._store_name(cleaned)
        invoice_number = self._invoice(cleaned)
        date           = self._date(cleaned)
        time_val       = self._time(cleaned)
        total_amount   = self._total(cleaned)
        vat_amount     = self._vat(cleaned)
        tin            = self._tin(cleaned)
        items          = self._items(cleaned)          # ← subclass implements this

        confidence = self._confidence_score(
            store_name, invoice_number, date, total_amount, items
        )

        result = {
            "store_name":            store_name,
            "invoice_number":        invoice_number,
            "date":                  date,
            "time":                  time_val,
            "total_amount":          total_amount,
            "vat_amount":            vat_amount,
            "tin":                   tin,
            "item_count":            sum(i.get("qty", 1) or 1 for i in items),
            "has_vat":               vat_amount is not None,
            "items":                 items,
            "extraction_confidence": confidence,
        }

        logger.info(
            f"[{self.__class__.__name__}] store={store_name!r} "
            f"invoice={invoice_number!r} date={date!r} "
            f"total={total_amount!r} items={len(items)} "
            f"confidence={confidence:.2f}"
        )
        return result

    # ── Shared field extractors ────────────────────────────────────────────────

    def _store_name(self, lines: List[str]) -> Optional[str]:
        """First non-trivial line — reliable for ALL Philippine receipts."""
        for line in lines[:8]:
            s = line.strip()
            if len(s) < 3:
                continue
            if re.match(r'^\d+$', s):
                continue
            if _SEPARATOR.match(s):
                continue
            if re.match(r'^\d+\.\d{2}', s):
                continue
            return s
        return None

    def _invoice(self, lines: List[str]) -> Optional[str]:
        """Two-pass: genuine invoice IDs first, TXN# only as fallback."""
        def _is_txn(p):
            s = p.pattern.upper()
            return 'TXN' in s or 'TRANSACTION' in s or 'CONTROL' in s

        high = [p for p in _INVOICE_PATTERNS if not _is_txn(p)]
        low  = [p for p in _INVOICE_PATTERNS if _is_txn(p)]

        for group in (high, low):
            for line in lines:
                for pat in group:
                    m = pat.search(line)
                    if m:
                        val = m.group(1).strip()
                        if len(val) >= 4:
                            return val
        return None

    def _date(self, lines: List[str]) -> Optional[str]:
        """
        Scan all lines for date across all supported formats.

        Priority groups (most → least specific):
          Group 1 — numeric + written with 4-digit year (unambiguous)
          Group 2 — 2-digit year (common on Philippine receipts)
          Group 3 — month-year only, ordinal forms (no full date)
          Group 4 — day/month only (last resort, easily confused with prices)
        """
        high_priority_pats   = _DATE_PATTERNS[:5]    # 4-digit year
        medium_priority_pats = _DATE_PATTERNS[5:8]   # 2-digit year
        low_priority_pats    = _DATE_PATTERNS[8:12]  # month-year, ordinal
        last_resort_pats     = _DATE_PATTERNS[12:]   # day/month only

        def _valid(m, line):
            after  = line[m.end():m.end()+1]
            before = line[m.start()-1:m.start()] if m.start() > 0 else ''
            if after == '-':       # range marker: "08/01/20-07/31/25"
                return False
            if before.isdigit():  # middle of a longer number
                return False
            return True

        # Round 1: short standalone lines (≤25 chars) — highest confidence
        for line in lines:
            s = line.strip()
            if len(s) > 25:
                continue
            for pat in high_priority_pats + medium_priority_pats:
                m = pat.search(s)
                if m and _valid(m, s):
                    return m.group(1).strip()

        # Round 2: any line, high+medium priority
        for line in lines:
            for pat in high_priority_pats + medium_priority_pats:
                m = pat.search(line)
                if m and _valid(m, line):
                    return m.group(1).strip()

        # Round 3: low priority — only on labeled date lines or short lines
        _DATE_CONTEXT = re.compile(
            r'\b(date|dated|issued|on|as\s+of|for)\b', re.IGNORECASE
        )
        for line in lines:
            s = line.strip()
            if not (_DATE_CONTEXT.search(s) or len(s) <= 20):
                continue
            for pat in low_priority_pats:
                m = pat.search(s)
                if m and _valid(m, s):
                    return m.group(1).strip()

        # Round 4: last resort day/month — only on explicitly labeled lines
        for line in lines:
            if not _DATE_CONTEXT.search(line):
                continue
            for pat in last_resort_pats:
                m = pat.search(line)
                if m and _valid(m, line):
                    return m.group(1).strip()

        # Round 5: TXN-embedded date (Mercury Drug)
        for line in lines:
            if re.match(r'TXN#?\d', line, re.IGNORECASE):
                d = self._txn_date(line)
                if d:
                    return d
        return None

    def _txn_date(self, line: str) -> Optional[str]:
        """
        Extract MM-DD-YY from Mercury Drug TXN lines in all OCR merge formats.

        Known formats:
          A — space after TXN number (clean OCR):
              "TXN#071432 11-01-25 09:29P RACKY"
          B — NO space, date runs directly into TXN number (most common):
              "TXN#93179911-13-25 03:36P p1lar"
              "TXN#03299910-19-2507:54PKAREN"
          C — fully squashed, dashes and spaces all dropped:
              "TXN#135330-101113-2509:11PDORIS"

        Strategy: scan ALL MM-DD-YY candidates in the line, validate each.
        First valid candidate (MM 01-12, DD 01-31, YY >= 20) wins.
        This handles all spacing variants without position-based slicing.
        """
        for m in re.finditer(r'(\d{2})-(\d{2})-(\d{2})', line):
            mm, dd, yy = m.group(1), m.group(2), m.group(3)
            try:
                mm_i, dd_i, yy_i = int(mm), int(dd), int(yy)
            except ValueError:
                continue
            if 1 <= mm_i <= 12 and 1 <= dd_i <= 31 and yy_i >= 20:
                return f"{mm}-{dd}-{yy}"
        # Format C: fully squashed digits — MMDD run together, then -YY
        m3 = re.search(r'TXN#?\d+[-](\d{2})(\d{2})\d{0,2}[\-](2\d)\d{2}:', line)
        if m3:
            mm, dd, yy = m3.group(1), m3.group(2), m3.group(3)
            try:
                if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                    return f"{mm}-{dd}-{yy}"
            except ValueError:
                pass
        return None

    def _time(self, lines: List[str]) -> Optional[str]:
        """Handles 02:15P single-letter suffix and full AM/PM."""
        for line in lines:
            for pat in _TIME_PATTERNS:
                m = pat.search(line)
                if m:
                    start = m.start()
                    if start > 0 and line[start - 1].isdigit():
                        continue
                    return m.group(1).strip()
        return None

    def _total(self, lines: List[str]) -> Optional[str]:
        """Inline format first, then split-line (keyword + next-line price)."""
        for pat in _TOTAL_PATTERNS:
            for line in lines:
                m = pat.search(line)
                if m:
                    try:
                        return f"₱{float(m.group(1).replace(',', '')):,.2f}"
                    except ValueError:
                        pass

        n = len(lines)
        for kw_pat in _TOTAL_KW_PRIORITY:
            for i, line in enumerate(lines):
                if kw_pat.match(line.strip()) and i + 1 < n:
                    price = self._price_of(lines[i + 1])
                    if price and price > 0:
                        return f"₱{price:,.2f}"
        return None

    def _vat(self, lines: List[str]) -> Optional[str]:
        """Inline then split-line."""
        for pat in _VAT_PATTERNS:
            for line in lines:
                m = pat.search(line)
                if m:
                    try:
                        val = float(m.group(1).replace(',', ''))
                        if val > 0:
                            return f"₱{val:,.2f}"
                    except ValueError:
                        pass

        n = len(lines)
        for i, line in enumerate(lines):
            if _VAT_KW.match(line.strip()) and i + 1 < n:
                price = self._price_of(lines[i + 1])
                if price and price > 0:
                    return f"₱{price:,.2f}"
        return None

    def _tin(self, lines: List[str]) -> Optional[str]:
        for pat in _TIN_PATTERNS:
            for line in lines:
                m = pat.search(line)
                if m:
                    return m.group(1).strip()
        return None

    # ── Must be overridden ────────────────────────────────────────────────────

    def _items(self, lines: List[str]) -> List[Dict]:
        """Subclasses implement layout-specific item extraction."""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _items()"
        )

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _price_of(self, line: str) -> Optional[float]:
        """Parse a standalone price line; returns float or None."""
        s = line.strip()
        # Reject qty-at-price lines like "3 @ 36.00"
        if re.match(r'^\d+\s*@\s*[\d,]+\.\d{2}$', s):
            return None
        # Normalize OCR character confusions on price-like lines.
        # "81.0OT" → "81.00T", "81.OOT" → "81.00T" (O mistaken for 0)
        if re.match(r'^[₱P]?\s*[\d\.,OIl]+\s*[TXZVvy]?\s*$', s, re.IGNORECASE):
            s = s.upper().replace('O', '0').replace('I', '1').replace('L', '1')
        # Normalize trailing '1' mistaken for 'T' on thermal receipts:
        # "261.001" → "261.00T" — only when exactly 2 decimal digits precede the '1'
        s = re.sub(r'(\d[\d,]+\.\d{2})1$', r'\1T', s)
        m = _PRICE_ONLY.match(s)
        if not m:
            return None
        try:
            return float(m.group(1).replace(',', ''))
        except ValueError:
            return None

    def _build_item(
        self,
        name: str,
        price: float,
        sku: Optional[str] = None,
        qty: Optional[int] = None,
        unit_price: Optional[float] = None,
        source_idx: int = 0,
    ) -> Dict:
        """Build a standardised item dict."""
        clean = name.strip()
        inferred_qty = 1
        m = re.match(r'^(\d+)\s*[xX]\s+(.+)$', clean)
        if m:
            inferred_qty = int(m.group(1))
            clean = m.group(2).strip()
        m2 = re.match(r'^(.+?)\s+[xX](\d+)\s*$', clean)
        if m2:
            clean = m2.group(1).strip()
            inferred_qty = int(m2.group(2))

        return {
            "name":       clean,
            "price":      round(price, 2),
            "qty":        qty if qty is not None else inferred_qty,
            "unit_price": unit_price,
            "sku":        sku,
            "_src":       source_idx,
        }

    def _confidence_score(
        self,
        store_name: Optional[str],
        invoice: Optional[str],
        date: Optional[str],
        total: Optional[str],
        items: List[Dict],
    ) -> float:
        """Produce a 0–1 confidence score based on what was extracted."""
        score = 1.0
        if not store_name:   score -= 0.15
        if not total:        score -= 0.25
        if not date:         score -= 0.10
        if not items:        score -= 0.20
        if not invoice:      score -= 0.05
        return round(max(0.0, score), 2)

    @staticmethod
    def _empty() -> Dict:
        return {
            "store_name":            None,
            "invoice_number":        None,
            "date":                  None,
            "time":                  None,
            "total_amount":          None,
            "vat_amount":            None,
            "tin":                   None,
            "item_count":            0,
            "has_vat":               False,
            "items":                 [],
            "extraction_confidence": 0.0,
        }