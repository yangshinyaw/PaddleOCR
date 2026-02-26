"""
General Metadata Extractor for Philippines Receipts
Version 2.0 - All bugs fixed

Bug fixes vs v1:
  FIX 1 - Store name: takes the FIRST non-trivial line unconditionally.
           Old version skipped lines containing words like RIZAL, ROAD, COMPLEX
           causing "MERCURY DRUG - RIZAL BANANGONAN EM COMPLEX" to be skipped
           and PA99S/S to become the store name instead.

  FIX 2 - Date: now detects MM-DD-YY embedded in TXN# lines
           e.g. "TXN#110855 11-13-25 02:15P EJ" -> date = "11-13-25"
           (was working in isolation but not when combined with time fix)

  FIX 3 - Time: handles single-letter suffix  02:15P / 02:15A
           Old pattern required full "AM"/"PM" so 02:15P was never matched.

  FIX 4 - Items (Mercury Drug format): OCR reads the price COLUMN before the
           item NAME column when columns are split across lines, producing:
               "1220.00T"          <- price
               "NIDO5+PDR MLK2kg"  <- name
               "480036140523"      <- barcode
           New algorithm does 3 passes: price-then-name, name-then-price, inline.

  FIX 5 - PA#99 S/S lines skipped: "PA99S/S" is a Mercury Drug prescription
           mode indicator, not an item name or store name.

  FIX 6 - Multi-image / stitched mode: receipt_processor.py now passes all
           OCR output (single AND stitched) through GeneralMetadataExtractor.
"""

import re
from typing import List, Dict, Optional

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ─── Compiled regexes ────────────────────────────────────────────────────────

# Quantity × unit-price lines: "4 @ 299.00", "30 @ 14.00", "84 @ 16.50"
# These appear on Mercury Drug receipts when an item has qty > 1
_QTY_LINE = re.compile(
    r'^(\d{1,4})\s*[@xX×]\s*([\d,]+\.\d{2})\s*$'
)

_SKIP_ITEM = re.compile(
    r'\b(TOTAL|SUBTOTAL|CHANGE|CASH|CARD|PAYMENT|TENDERED|DISCOUNT|LESS|'
    r'VAT|TAX|BALANCE|DUE|PAID|AMOUNT|VOID|REFUND|TIN|DATE|TIME|CASHIER|'
    r'THANK|WELCOME|PLEASE|COME|AGAIN|SAVE|SENIOR|PWD|MEMBER|POINTS|LOYALTY|'
    r'DEBIT|CREDIT|NET|GROSS|INVOICE|SOLD|ADDRESS|VATAble|Exempt|Zero|Rated|'
    r'Phillogix|Accred|PTU|MIN|TXN|TOSHIBA|MOBILE|VIBER|BRGY|BARANGAY|'
    r'RECEIPT|YOUR|THIS|MERCHANDISE|CONDITION|SALAMAT|MARAMING|LAGING|'
    r'NAKASISIGURO|GAMOT|BAGO|items?)\b',
    re.IGNORECASE
)

# Payment method lines — never item names
# Covers abbreviated forms OCR produces: "CRED CRD", "GCASH", "PAYMAYA", etc.
_PAYMENT_METHOD = re.compile(
    r'^(CRED\s*CRD|CRED\s*CARD|DEBIT\s*CRD|DEBIT\s*CARD|'
    r'GCASH|G\s*CASH|PAYMAYA|MAYA|PAYPAL|'
    r'UNIONPAY|UNION\s*PAY|VISA|MASTERCARD|MASTER\s*CARD|'
    r'AMEX|JCB|BDO|BPI|METROBANK|CHINABANK|RCBC|PNB|LANDBANK|DBP|'
    r'CHECK|CHEQUE|VOUCHER|E\s*WALLET|EWALLET|'
    r'APPROVAL|APPROVAL\s*#|ORDER\s*#|CARD\s*#|CARD\s*NUMBER|'
    r'SOLD\s*TO|SOLDTO|PAYMAYA|'
    r'SUKI\s*#|SUKI\s*POINTS|NAME\s*:)'
    r'.*$'
    # SM / supermarket loyalty & receipt-footer lines
    r'|^MEMBER\s+(N[AO]NE|NAME|NO|ID|CARD)\b'   # MEMBER NANE:, MEMBER NAME:
    r'|^ITEMS?\s+PURCHAS'                         # ITEMS PURCHASED : 8, ITEMS PURCHASEO
    # VAT breakdown section (always after CHANGE / payment, never items)
    r'|^VAT(?:ABLE|EBLE|ABLE|EABLE)?\s*SALE'     # VATable Sale, Vateble Sale, Vatable Sale
    r'|^VAT(?:\s*EXEMPT|\s*ZERO|\s*\()'           # VAT Exempt Sale, VAT Zero Rated, VAT(12%)
    r'|^ZERO\s+RATED\s+SALE'                      # Zero Rated Sale
    r'|^VAT\s+EXEMPT\s+SALE'
    # Blank form fields (SM footer)
    r'|^(NANE|NANS|NAME|ADDRESS|TIN|BUSINESS\s*STYLE)\s*:\s*$',
    re.IGNORECASE
)

# System / machine / footer lines that must never be items
_METADATA_JUNK = re.compile(
    # Machine identifiers
    r'^(TOSHIBA|POSTEK|EPSON|CASIO|NCR|SAMSUNG)\b'        # POS terminal brand
    r'|^MIN\d{10,}'                                          # MIN: machine ID number
    r'|\[\d+\.\d+\.\d+\]'                            # firmware version [1.5.30]
    # Phillogix footer lines
    r'|^Phillogix'
    r'|^433\s*Lt\.?\s*Artiaga'                           # head office address
    r'|^PTU\s*No\.?'                                       # PTU accreditation
    r'|^Accred\s*No'                                        # Accreditation number
    r'|^VAT\s*REG\s*TIN\s*\d'                           # VAT TIN line (starts with digits after)
    # Credit card transaction junk
    r'|^Approva[l1]\s*#'                                   # Approval# (OCR: l→1)
    r'|^Card\s*#\s*\*+'                                  # Card #****
    # PWD/SC transaction header
    r'|^PWDID\s*#'
    r'|^SUKI\s*#'
    r'|^NAME\s*:.*\*'                                      # NAME:AL****N (masked name)
    # Blank form fields
    r'|^(SIGNATURE|SOLD\s*TO|ADDRESS|TIN\s*NO|BUSINES\s*STYLE)\s*:?\s*_{0,}$'
    r'|^-{5,}$'                                              # separator dashes
    r'|^={5,}$'                                              # separator equals
    # Masked customer info
    r'|^NAME[:\s].*\*{3,}'                                 # NAME:AL****N
    # SM / supermarket machine/footer lines
    r'|^SN#\S+'                                             # SN#59HYN21948...
    r'|^Vincor\s+Nixdorf'                                   # POS vendor footer
    r'|^SALESINVOICE\d'                                     # SALESINVOICE000126613...
    r'|^\d{9,}[A-Z]{2,}'                                    # 007242095000RCC... (machine ref)
    r'|^[A-Z]\d{2,}[A-Z]\d+[A-Z]\d+'                       # B66C350211083D58016 (receipt code)
    r'|^O\s+Lite\s*$'                                       # "O Lite" footer marker
    # Note: city/address lines ("Malhacan Meycauayan", "Bulacan") are handled
    # by the item-zone guard in _items() — they appear before the PA# line
    # and are never searched. No regex needed here (would falsely block product names).
    ,
    re.IGNORECASE
)

# Mercury Drug discount/flag lines that must never be items
# *BP = blood pressure discount marker
# LESSBPDISC = "LESS: BP DISC" merged by OCR — it's a discount line
# (T), (X), (Z) = taxability suffixes on Mercury Drug receipts
_MERCURY_JUNK = re.compile(
    r'^\*[A-Z]{1,4}$'                     # *BP, *SC, *PWD — discount markers
    r'|^\([TXZSE]\)$'                     # (T) (X) (Z) — taxability markers
    r'|LESS\s*:?\s*BP\s*DISC'            # LESS : BP DISC
    r'|LESSBPDISC'                           # merged OCR version
    r'|^LESS\b.*\bDISC\b'               # any LESS...DISC combination
    r'|^\*{1,2}[A-Z0-9\s]{1,6}\*{0,2}$' # **SC** **PWD** type markers
    r'|^[\(\[][TXZSEPWDB]{1,3}[\)\]]$', # (T) [T] (PWD) bracket markers
    re.IGNORECASE
)

# Mercury Drug prescription mode indicator: PA99S/S or PA # 99 S/S
_PA_MODE = re.compile(
    r'^PA\s*#?\s*\d+\s*S/S$'                  # PA#99 S/S, PA # 99 S/S
    r'|^PA\s*#?\s*\d+\s*\w{0,8}$'            # PA#9MICH, PA#99, PA # 9 EJ
    r'|^PA\s*#\s*\d+\s+[A-Za-z][A-Za-z-]{0,12}$',  # PA # 11 Jay-R (cashier)
    re.IGNORECASE
)

_BARCODE = re.compile(r'^\d{6,14}$')

# Quantity × unit-price line: "3 @ 36.00" or "10 @ 6.75" or "3@36.00"
# These are OCR'd from Mercury Drug's two-column layout where qty and unit price
# appear on a separate line between item name and total price.
# When columns merge, "3 @ 36.00" becomes "336.00" — a fake price.
# We detect and skip these BEFORE they are misread as standalone prices.
_QTY_AT_PRICE = re.compile(
    r'^\d+\s*@\s*[\d,]+\.\d{2}$'   # "3 @ 36.00" or "10@6.75"
    r'|^\d+\s+@\s+[\d,]+\.\d{2}$', # with spaces: "3 @ 36.00"
)
_SEPARATOR = re.compile(r'^[\-\*\=\s\.]+$|^\*\*.*\*\*$')  # also matches ** 6 item(s) **

# Receipt's own stated item count: "** 2 item(s) **" or "* 16 items *"
# item(s) uses escaped parens; also handles plain "items" and "item"
_ITEM_COUNT_LINE = re.compile(
    r'\*+\s*(\d+)\s*item(?:s|\(s\))?\s*\*+',
    re.IGNORECASE
)

# Price-only line: optional ₱/P prefix, digits, 2 decimal places, optional T/X/Z taxability suffix
_PRICE_ONLY = re.compile(r'^[₱P]?\s*([\d,]+\.\d{2})[TXZ]?\s*$')

# Inline price: "ITEM NAME   123.45T"  (2+ space gap)
_PRICE_INLINE = re.compile(r'^(.+?)\s{2,}[₱P]?\s*([\d,]+\.\d{2})[TXZ]?\s*$')

# ── Date patterns (most → least specific) ────────────────────────────────────
_DATE_PATTERNS = [
    re.compile(r'\b(\d{2}[/-]\d{2}[/-]\d{4})\b'),          # 01/28/2026
    re.compile(r'\b(\d{4}[/-]\d{2}[/-]\d{2})\b'),          # 2026-01-28
    re.compile(r'\b(\d{2}[/-]\d{2}[/-]\d{2})\b'),          # 11-13-25  ← Mercury Drug
    re.compile(r'\b(\d{1,2}\s+\w{3,9}\s+\d{4})\b'),        # 28 January 2026
    re.compile(r'\b(\w{3,9}\.?\s+\d{1,2},?\s+\d{4})\b'),   # January 28, 2026
]

# ── Time patterns — handles 02:15P (single-letter suffix) ────────────────────
_TIME_PATTERNS = [
    re.compile(r'\b(\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM|[AP]M?)?)\b', re.IGNORECASE),
    re.compile(r'\b(\d{1,2}:\d{2}\s*[AP]M?)\b', re.IGNORECASE),  # 02:15P or 02:15PM
    re.compile(r'\b(\d{1,2}:\d{2}\s*(?:AM|PM))\b', re.IGNORECASE),
]

# ── Invoice patterns (priority order: INVOICE# first, TXN# second) ───────────
_INVOICE_PATTERNS = [
    re.compile(r'\bSALESINVOICE\s*(\d{6,})', re.IGNORECASE),           # SALESINVOICE000126613
    re.compile(r'\bINVOICE\s*#\s*(\d{4,})', re.IGNORECASE),           # INVOICE#110703137533
    re.compile(r'\bINVOICE\s*#\s*([A-Z0-9\-]{4,})', re.IGNORECASE),
    re.compile(r'\b(?:OR|SI)\s*#\s*([A-Z0-9][A-Z0-9\-]{3,})', re.IGNORECASE),
    re.compile(r'\b(?:O\.R\.|S\.I\.)\s*#?\s*:?\s*([A-Z0-9\-]{4,})', re.IGNORECASE),
    re.compile(r'\b(?:OFFICIAL RECEIPT|SALES INVOICE|RECEIPT NO\.?)\s*#?\s*:?\s*([A-Z0-9\-]{4,})', re.IGNORECASE),
    re.compile(r'\bTXN\s*#\s*(\w{4,})', re.IGNORECASE),               # TXN#110855 (lower priority)
    re.compile(r'\b(?:TRANSACTION|CONTROL)\s*(?:NO\.?|#)\s*:?\s*([A-Z0-9\-]{4,})', re.IGNORECASE),
]

# ── Total amount patterns ─────────────────────────────────────────────────────
_TOTAL_PATTERNS = [
    re.compile(r'GRAND\s+TOTAL\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'TOTAL\s+AMOUNT\s+DUE\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'AMOUNT\s+DUE\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'TOTAL\s+PAYMENT\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'TOTAL\s+SALES\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'NET\s+AMOUNT\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'(?<!\w)TOTAL\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
]

# ── VAT patterns ──────────────────────────────────────────────────────────────
_VAT_PATTERNS = [
    re.compile(r'(?:VAT\s*[-–]?\s*12%|12%\s*VAT|OUTPUT\s*TAX|VAT\s*AMOUNT)\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    re.compile(r'VAT\s*[:\-]?\s*[₱P]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
]

# ── Product indicator patterns ───────────────────────────────────────────────
# These appear in real product names and NOT in financial summary lines.
# Used to rescue lines that contain a financial keyword but are actually items.
_PRODUCT_UNITS = re.compile(
    # Match numeric+unit (500ML, 1.5KG) OR standalone unit word (BOX, PCS, TAB)
    r'(\d+\.?\d*\s*(?:ML|L|KG|G|MG|PCS|PC|TAB|CAP|TABS|CAPS|BOX|BTL|PKT|PCK|'
    r'SACHET|POUCH|ROLL|PAIR|SET|SHEET|BAG|CAN|JAR|TUB|TUBE|OZ|LB|GM|GMS|KCAL|MCG|IU)'
    r'|(?<![A-Za-z])(?:ML|KG|MG|PCS|TAB|TABS|CAPS|CAP|BOX|BTL|PKT|PCK|SACHET|POUCH|'
    r'ROLL|PAIR|SET|BAG|CAN|JAR|TUB|TUBE|OZ|LB|GM|GMS)(?![A-Za-z]))',
    re.IGNORECASE
)

# Alphanumeric product code: mix of letters and digits like "C2", "3IN1", "NIDO5+"
# Must be a standalone token (not just any letter+digit combo inside a word).
# Excludes known financial suffixes: VAT12%, TAX5%, etc.
# Minimum 2 chars on each side to avoid matching "T" in "500T" taxability suffix.
_PRODUCT_CODE = re.compile(
    r'(?<![A-Za-z])([A-Z]{2,}\d+|\d+[A-Z]{2,})(?![A-Za-z%])',
    re.IGNORECASE
)

# Financial-only lines: these patterns = definitely NOT a product
# Used as a secondary hard filter regardless of product indicators
_FINANCIAL_LINE = re.compile(
    r'^(SUBTOTAL|SUBTOIAL|SUBT0TAL|SUB\s*TOTAL|GRAND\s*TOTAL|'
    r'TOTAL\s*AMOUNT|AMOUNT\s*DUE|'
    r'TOTAL\s*PAYMENT|TOTAL\s*SALES|NET\s*AMOUNT|NET\s*SALES|'
    r'CASH\s*TENDERED|AMOUNT\s*TENDERED|TOTAL\s*TENDERED|'
    r'CHANGE|CHANG3|CH4NGE|BALANCE|CASH|DEBIT|CREDIT|VAT|TAX|DISCOUNT|'
    r'VATABLE|VAT[\s\-]*EXEMPT|ZERO[\s\-]*RATED|OUTPUT\s*TAX|'
    r'TOTAL|TOTAI|T0TAL|T0TAI|T0TALS?|VAT\s*[-–]?\s*\d+%?)\s*[:\-₱P\d\.]*\s*$',
    re.IGNORECASE
)

# OCR-normalized check: replace common OCR confusions before financial keyword check
# so "T0TAL" and "TOTAI" both match "TOTAL"
def _normalize_for_skip(text: str) -> str:
    """Normalize OCR confusions for financial keyword detection only."""
    t = text.upper()
    t = t.replace('0', 'O').replace('1', 'I').replace('|', 'I')
    t = t.replace('5', 'S').replace('8', 'B').replace('6', 'G')
    return t

# ── TIN patterns ──────────────────────────────────────────────────────────────
_TIN_PATTERNS = [
    re.compile(r'(?:VAT\s+REG\s+)?TIN\s*[:\-]?\s*(\d{3}[\-\s]\d{3}[\-\s]\d{3}[\-\s\d]+)', re.IGNORECASE),
    re.compile(r'TIN\s*[:\-]?\s*(\d{9,15})', re.IGNORECASE),
]


# ─────────────────────────────────────────────────────────────────────────────

class GeneralMetadataExtractor:
    """
    Extract structured metadata from raw OCR text lines for Philippines receipts.
    Works with single images AND stitched/multi-image output.
    """

    def extract(self, text_lines: List[str]) -> Dict:
        """
        Args:
            text_lines: Raw OCR text strings (one per detected line).
        Returns:
            Dict: store_name, invoice_number, date, time, total_amount,
                  vat_amount, tin, item_count, has_vat, items
        """
        if not text_lines:
            return self._empty()

        cleaned = [l.strip() for l in text_lines if l.strip()]
        if not cleaned:
            return self._empty()

        # stated_item_count MUST scan raw lines — "** 2 item(s) **" is caught
        # by _SEPARATOR and would be stripped from `cleaned` before _items() runs
        stated_count   = self._stated_item_count(cleaned)

        store_name     = self._store_name(cleaned)
        invoice_number = self._invoice(cleaned)
        date           = self._date(cleaned)
        time_val       = self._time(cleaned)
        total_amount   = self._total(cleaned)
        vat_amount     = self._vat(cleaned)
        tin            = self._tin(cleaned)
        items          = self._items(cleaned)

        # Post-extraction validation: remove fake items using price-sum and count
        items = self._validate_items(items, total_amount, stated_count)

        result = {
            'store_name':     store_name,
            'invoice_number': invoice_number,
            'date':           date,
            'time':           time_val,
            'total_amount':   total_amount,
            'vat_amount':     vat_amount,
            'tin':            tin,
            'item_count':     sum(i.get('qty', 1) or 1 for i in items),
            'stated_item_count': stated_count,
            'has_vat':        vat_amount is not None,
            'items':          items,
        }

        logger.info(
            f"[Extractor] store={store_name!r} invoice={invoice_number!r} "
            f"date={date!r} time={time_val!r} total={total_amount!r} "
            f"lines={len(items)} items={sum(i.get('qty',1) or 1 for i in items)}"
        )
        return result

    # ── Store name ────────────────────────────────────────────────────────────

    def _store_name(self, lines: List[str]) -> Optional[str]:
        """
        FIX 1: Take the FIRST non-trivial line as the store name.

        The old approach tried to skip lines with location words (RIZAL, ROAD, etc.)
        which caused the actual store name to be skipped. The store name is
        reliably the very first real text line on any receipt.

        Non-trivial = not pure digits, not a separator line, at least 3 chars,
        doesn't start with a price.
        """
        for line in lines[:8]:
            s = line.strip()
            if len(s) < 3:
                continue
            if re.match(r'^\d+$', s):           # pure digits
                continue
            if _SEPARATOR.match(s):             # ---, ***, ===
                continue
            if re.match(r'^\d+\.\d{2}', s):    # starts with a price amount
                continue
            return s
        return None

    # ── Invoice ───────────────────────────────────────────────────────────────

    def _invoice(self, lines: List[str]) -> Optional[str]:
        """
        Prefer INVOICE# over TXN# (two-pass search).
        """
        priority = _INVOICE_PATTERNS[:2]    # INVOICE# patterns
        rest = _INVOICE_PATTERNS[2:]        # OR#, TXN#, etc.

        for group in (priority, rest):
            for line in lines:
                for pat in group:
                    m = pat.search(line)
                    if m:
                        val = m.group(1).strip()
                        if len(val) >= 4:
                            return val
        return None

    # ── Date ─────────────────────────────────────────────────────────────────

    def _date(self, lines: List[str]) -> Optional[str]:
        """
        Scan all lines for date. Handles three formats:

        1. Standard patterns (MM/DD/YYYY, YYYY-MM-DD, MM-DD-YY, etc.)
           Works on any line.

        2. TXN line with spaces (clear OCR):
           "TXN#071432 11-01-25 09:29P RACKY" → 11-01-25

        3. TXN line with spaces dropped (merged OCR):
           "TXN#135330-101113-2509:11PDORIS"  → 10-11-25
           "TXN#03299910-19-2507:54PKAREN"    → 10-19-25
           The date digits are embedded with OCR-merged separators.
        """
        # Pass 1: standard patterns on all lines
        # Two rounds:
        #   Round A: standalone date lines (line is only the date or date + short suffix)
        #   Round B: date embedded in longer line — but skip if followed by '-'
        #            (dash after date = accreditation period range like "08/01/20-07/31/25")

        # Round A: standalone / short lines first (highest confidence)
        for line in lines:
            s = line.strip()
            if len(s) > 20:
                continue    # skip long lines in this round
            for pat in _DATE_PATTERNS:
                m = pat.search(s)
                if m:
                    after = s[m.end():m.end()+1]
                    if after != '-':    # not a range start
                        return m.group(1).strip()

        # Round B: any line, but exclude date-range starts
        for line in lines:
            for pat in _DATE_PATTERNS:
                m = pat.search(line)
                if m:
                    after = line[m.end():m.end()+1]
                    if after != '-':    # skip "08/01/20-" range markers
                        return m.group(1).strip()

        # Pass 2: TXN-specific extraction for merged/garbled lines
        for line in lines:
            if not line.upper().startswith('TXN#'):
                continue
            date = self._extract_txn_date(line)
            if date:
                return date
        return None

    def _extract_txn_date(self, line: str) -> Optional[str]:
        """
        Extract MM-DD-YY from Mercury Drug TXN lines in all OCR merge formats.

        Format A — spaces intact (normal OCR):
          "TXN#071432 11-01-25 09:29P RACKY"
          Strip the TXN#number and find MM-DD-YY in the body.

        Format B — date dashes kept, spaces dropped, TXN# glued to date:
          "TXN#03299910-19-2507:54PKAREN"
          The pattern MM-DD-YY(2-digit) is present with dashes but no spaces.

        Format C — fully squashed, date digits run together, separated by dash from YY:
          "TXN#135330-101113-2509:11PDORIS"
          "101113" = MM(10) + DD(11) + OCR-noise, then "-25" = YY, then time.
        """
        import re as _re

        # Format A: space after TXN#number → extract date from body
        body_m = _re.match(r'TXN#\d+\s(.+)', line)
        if body_m:
            body = body_m.group(1)
            m = _re.search(r'(\d{2})-(\d{2})-(\d{2})', body)
            if m:
                mm, dd, yy = m.group(1), m.group(2), m.group(3)
                if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                    return f"{mm}-{dd}-{yy}"

        # Format B: date dashes kept but no spaces
        # MM-DD-YY(2-digit) followed immediately by time digits "HH:MM" or "[AP]M"
        m2 = _re.search(r'(\d{2})-(\d{2})-(2\d)(?=\d{2}:|\d{1}[AP])', line)
        if m2:
            mm, dd, yy = m2.group(1), m2.group(2), m2.group(3)
            if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                return f"{mm}-{dd}-{yy}"

        # Format C: squashed digits — MMDD[noise]-YY[time]
        # After TXN#[digits]-: next 4 digits = MM+DD, skip noise, then -YY, then HH:MM
        m3 = _re.search(r'TXN#\d+[-](\d{2})(\d{2})\d{0,2}[\-](2\d)\d{2}:', line)
        if m3:
            mm, dd, yy = m3.group(1), m3.group(2), m3.group(3)
            if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                return f"{mm}-{dd}-{yy}"

        return None

    # ── Time ─────────────────────────────────────────────────────────────────

    def _time(self, lines: List[str]) -> Optional[str]:
        """
        FIX 3: Handles 02:15P (single P/A suffix) in addition to full AM/PM.
        """
        for line in lines:
            for pat in _TIME_PATTERNS:
                m = pat.search(line)
                if m:
                    # Guard: don't match a time that's really part of a longer number
                    start = m.start()
                    if start > 0 and line[start - 1].isdigit():
                        continue
                    return m.group(1).strip()
        return None

    # ── Total ─────────────────────────────────────────────────────────────────

    def _total(self, lines: List[str]) -> Optional[str]:
        """
        Find total amount. Handles two formats:
          Inline: "TOTAL  2003.50"  (keyword + amount on same line)
          Split:  "TOTAL"           (keyword on one line)
                  "2003.50"         (amount on next line)
        Uses TOTAL_PAYMENT > TOTAL to avoid picking up intermediate totals.
        """
        n = len(lines)

        # Pass 1: inline format (existing logic — most specific patterns first)
        for pat in _TOTAL_PATTERNS:
            for line in lines:
                m = pat.search(line)
                if m:
                    try:
                        return f"₱{float(m.group(1).replace(',', '')):,.2f}"
                    except ValueError:
                        pass

        # Pass 2: split-line format — keyword on one line, price on next line.
        # Priority order matters: specific keywords BEFORE plain "TOTAL".
        # Plain "TOTAL" often appears as a subtotal BEFORE discounts;
        # "TOTAL AMOUNT" / "TOTAL PAYMENT" / "AMOUNT DUE" are the final totals.
        _TOTAL_KW_PRIORITY = [
            re.compile(r'^GRAND\s+TOTAL\s*[:\-]?\s*$', re.IGNORECASE),
            re.compile(r'^TOTAL\s+AMOUNT\s+DUE\s*[:\-]?\s*$', re.IGNORECASE),
            re.compile(r'^TOTAL\s+AMOUNT\s*[:\-]?\s*$', re.IGNORECASE),
            re.compile(r'^TOTAL\s+SALES\s*[:\-]?\s*$', re.IGNORECASE),
            re.compile(r'^NET\s+AMOUNT\s*[:\-]?\s*$', re.IGNORECASE),
            re.compile(r'^AMOUNT\s+DUE\s*[:\-]?\s*$', re.IGNORECASE),
            re.compile(r'^SUB\s*TOTAL\s*[:\-]?\s*$', re.IGNORECASE),  # SM Supermarket
            re.compile(r'^TOTAL\s*[:\-]?\s*$', re.IGNORECASE),         # plain TOTAL
            re.compile(r'^TOTAL\s+PAYMENT\s*[:\-]?\s*$', re.IGNORECASE),  # LAST: can equal tender
        ]
        for kw_pat in _TOTAL_KW_PRIORITY:
            for i, line in enumerate(lines):
                if kw_pat.match(line.strip()) and i + 1 < n:
                    price = self._price_of(lines[i + 1])
                    if price and price > 0:
                        return f"₱{price:,.2f}"
        return None

    # ── VAT ──────────────────────────────────────────────────────────────────

    def _vat(self, lines: List[str]) -> Optional[str]:
        """
        Find VAT amount. Handles inline and split-line format.
        Also handles "VAT12%" on one line and "214.66" on the next.
        """
        n = len(lines)

        # Pass 1: inline format
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

        # Pass 2: split-line — VAT keyword line then price line
        _VAT_KW = re.compile(
            r'^(VAT\s*[-–]?\s*\d*\s*%?|VAT\s+AMOUNT|OUTPUT\s+TAX|VAT)\s*[:\-]?\s*$',
            re.IGNORECASE
        )
        for i, line in enumerate(lines):
            if _VAT_KW.match(line.strip()) and i + 1 < n:
                price = self._price_of(lines[i + 1])
                if price and price > 0:
                    return f"₱{price:,.2f}"
        return None

    # ── TIN ──────────────────────────────────────────────────────────────────

    def _tin(self, lines: List[str]) -> Optional[str]:
        for pat in _TIN_PATTERNS:
            for line in lines:
                m = pat.search(line)
                if m:
                    return m.group(1).strip()
        return None

    # ── Items ─────────────────────────────────────────────────────────────────

    def _items(self, lines: List[str]) -> List[Dict]:
        """
        Four-pass item extraction handles all Philippine receipt formats.

        Item zone guard: Mercury Drug (and most Philippine pharmacies) print
        a "PA # 99 S/S" or "PA#9MICH" marker line immediately before the first
        item. Everything ABOVE that marker is store header / machine info.
        We restrict item search to lines AFTER the PA marker to prevent
        header lines (store name, address, machine IDs) from being falsely
        paired with stray price numbers.

        Pass A — price → name (Mercury Drug / column-OCR format):
            OCR reads right price-column before left name-column, producing:
            "1220.00T"          price line
            "NIDO5+PDR MLK2kg"  item name  (next unused line)
            "480036140523"      barcode     (optional)

        Pass B — name → barcode → price (3-line format, no leading price):
            "JUJU LPOP/RNG15g"  item name  (no price-only line immediately before it)
            "480652561024"      barcode
            "24.50T"            price

        Pass C — name → price (classic 2-line format):
            "BIOGESIC TAB"      item name
            "45.00"             price line

        Pass D — inline (name and price on same line):
            "POLO SHIRT BLUE M     599.00T"

        Key rule for Pass B: only fires when NO unused price-only line
        immediately precedes the name (which would mean Pass A should handle it).
        """
        n = len(lines)
        used: set = set()
        items: list = []

        # ── Item zone: items only appear between the header marker and SUBTOTAL ──
        #
        # START markers (first one found wins):
        #   Mercury Drug: "PA#99 S/S", "PA#9MICH" etc.
        #   SM / supermarkets: "PHP" (currency header printed before item list)
        #   Fallback: use line 0 (no restriction)
        #
        # END marker: SUBTOTAL, TOTAL, CHANGE DUE — items never appear after these.
        # This is critical for SM receipts which print loyalty card, VAT breakdown,
        # and footer info after the payment section.
        _ZONE_END = re.compile(
            r'^(SUBTOTAL|SUB\s*TOTAL|GRAND\s*TOTAL|CHANGE|CHANGE\s*DUE|'
            r'AMOUNT\s*TENDERED|CASH\s*TENDERED|TOTAL\s*PAYMENT)\s*[:\-]?\s*$',
            re.IGNORECASE
        )
        _ZONE_START_EXTRA = re.compile(
            r'^PHP\s*$',   # SM Supermarket currency header before items
            re.IGNORECASE
        )
        item_zone_start = 0
        item_zone_end = n    # default: search entire receipt
        for idx, line in enumerate(lines):
            s = line.strip()
            # Find start: PA# (Mercury) or PHP (SM)
            if item_zone_start == 0 and (
                _PA_MODE.match(s) or _ZONE_START_EXTRA.match(s)
            ):
                item_zone_start = idx + 1
                used.add(idx)   # mark zone-start line as used → never an item name
            # Find end: first SUBTOTAL/TOTAL/CHANGE after start
            if item_zone_start > 0 and idx > item_zone_start and _ZONE_END.match(s):
                item_zone_end = idx
                break

        # Pre-collect known financial amounts to exclude from items
        skip_prices = self._collect_financial_prices(lines)

        # ── Pass A: price → name (→ optional barcode) ──────────────────────
        # Mercury Drug column format: price printed BEFORE item name in OCR output
        # "108.00T"          ← price (with taxability suffix T/X/Z)
        # "ASMALIN PULMO1MG" ← item name
        # "480778822064"     ← barcode
        #
        # Two-phase: first pass only on TAXED prices (T/X/Z suffix) — high confidence.
        # These are unambiguously item prices on Mercury Drug receipts.
        # Second phase handles untaxed prices with extra validation.

        # ── Pass B2: name → barcode → qty_line → price ───────────────────────
        # Mercury Drug format when qty > 1:
        #   "CENTRUM ADV T-30"    ← name
        #   "480015330215"        ← barcode
        #   "4 @ 299.00"          ← qty × unit price line
        #   "1196.00T"            ← total price (taxed)
        # Note: no _has_price_before check here — the previous item's price will
        # always be "before" this name, which is normal and must not block detection.
        for i, line in enumerate(lines[item_zone_start:item_zone_end], start=item_zone_start):
            if i in used:
                continue
            if not self._is_name(line, n, i):
                continue
            j = i + 1   # expected barcode
            if j >= n or j in used or not self._is_barcode(lines[j]):
                continue
            k = j + 1   # expected qty line
            if k >= n or k in used:
                continue
            qty, unit_price = self._parse_qty_line(lines[k])
            if qty is None:
                continue
            m_idx = k + 1   # expected total price
            if m_idx >= n or m_idx in used:
                continue
            price = self._price_of(lines[m_idx])
            if price and price > 0 and price not in skip_prices:
                items.append(self._build(
                    line.strip(), price, lines[j].strip(),
                    qty=qty, unit_price=unit_price, source_idx=i
                ))
                used |= {i, j, k, m_idx}


        # A1b: name → junk → taxed price (handles *BP / *SC / *PWD markers
        #      that Mercury Drug inserts between item name and price)
        #   "NID05+PDR MLK2kg"  ← name
        #   "*BP"               ← discount marker (junk, skip)
        #   "1220.00T"          ← taxed price
        #   "480036140523"      ← barcode (optional)
        for i, line in enumerate(lines[item_zone_start:item_zone_end], start=item_zone_start):
            if i in used:
                continue
            if not self._is_name(line, n, i):
                continue
            # Use _next_price to find price, skipping junk in between
            j = self._next_price(i + 1, n, used, lines, max_skip=3)
            if j is None:
                continue
            if not self._is_taxed_price(lines[j]):
                continue
            price = self._price_of(lines[j])
            if price is None or price <= 0 or price in skip_prices:
                continue
            # Collect junk indices between name and price to mark as used
            junk_indices = set()
            for k in range(i + 1, j):
                if k not in used:
                    junk_indices.add(k)
            sku, m = self._maybe_barcode(j + 1, n, used, lines)
            items.append(self._build(line.strip(), price, sku, source_idx=i))
            used |= ({i, j} | junk_indices | ({m} if m is not None else set()))


        # A1a (runs AFTER B2 and A1b to avoid stealing their items)
        # A1a: forward — price at i, name at next line
        # GUARD: skip if the receipt layout is actually name→barcode→[qty]→price
        # (i.e. there is a barcode 1-3 lines BEFORE this price that has a name before it).
        # In that case, Pass B / B2 is the correct handler — A1a must not steal the price.
        for i, line in enumerate(lines[item_zone_start:item_zone_end], start=item_zone_start):
            if i in used:
                continue
            if not self._is_taxed_price(line):
                continue
            price = self._price_of(line)
            if price is None or price <= 0:
                continue
            if price in skip_prices:
                continue

            # Backward guard: look up to 3 unused lines before this price.
            # If we find: barcode ← name (i.e. name→barcode→[qty]→price layout),
            # Pass B/B2 will handle it — skip A1a here to avoid wrong pairing.
            _skip_a1a = False
            for back in range(1, 4):
                bi = i - back
                if bi < item_zone_start or bi in used:
                    break
                bs = lines[bi].strip()
                if self._is_barcode(bs):
                    # Found barcode before the price. Check if there's a name before the barcode.
                    ni = bi - 1
                    while ni >= item_zone_start and ni in used:
                        ni -= 1
                    if ni >= item_zone_start and self._is_name(lines[ni], n, ni):
                        _skip_a1a = True
                    break
                # qty line between barcode and price — keep looking back
                if _QTY_LINE.match(bs):
                    continue
                # Any other non-junk content → stop
                if not _MERCURY_JUNK.search(bs) and not _SEPARATOR.match(bs):
                    break
            if _skip_a1a:
                continue

            j = self._next_free(i + 1, n, used)
            if j is None:
                continue
            if self._is_name(lines[j], n, j):
                sku, k = self._maybe_barcode(j + 1, n, used, lines)
                items.append(self._build(lines[j].strip(), price, sku, source_idx=j))
                used |= ({i, j} | ({k} if k is not None else set()))


        # Phase A2: untaxed price → name (for receipts without T/X/Z suffix)
        # Extra guard: if the line AFTER the name is ALSO a valid price,
        # that following price is more likely the real item price (Pass B/C will handle it).
        # So we only assign an untaxed leading price if no price follows the name.
        for i, line in enumerate(lines[item_zone_start:item_zone_end], start=item_zone_start):
            if i in used:
                continue
            if self._is_taxed_price(line):
                continue   # already handled in A1
            price = self._price_of(line)
            if price is None or price <= 0:
                continue
            if price in skip_prices:
                continue
            j = self._next_free(i + 1, n, used)
            if j is None:
                continue
            if not self._is_name(lines[j], n, j):
                continue
            # Check: is there another price immediately after the name?
            # If yes, that next price is the real item price → skip this leading price
            k_after = self._next_free(j + 1, n, used)
            if k_after is not None:
                next_price = self._price_of(lines[k_after])
                if next_price and next_price > 0 and next_price not in skip_prices:
                    continue   # real price follows name → don't use leading untaxed price
            sku, k = self._maybe_barcode(j + 1, n, used, lines)
            items.append(self._build(lines[j].strip(), price, sku, source_idx=j))
            used |= ({i, j} | ({k} if k is not None else set()))


        # ── Pass B: name → barcode → price (only when no leading price) ────
        # Requires strict adjacency: name at i, barcode at i+1, price at i+2
        # (no skipping over used lines — prevents wrong price assignment)
        for i, line in enumerate(lines[item_zone_start:item_zone_end], start=item_zone_start):
            if i in used:
                continue
            if not self._is_name(line, n, i):
                continue
            if self._has_price_before(lines, i, used):
                continue
            j = i + 1
            if j >= n or j in used or not self._is_barcode(lines[j]):
                continue
            k = j + 1
            if k >= n or k in used:
                continue
            price = self._price_of(lines[k])
            if price and price > 0 and price not in skip_prices:
                items.append(self._build(line.strip(), price, lines[j].strip(), source_idx=i))
                used |= {i, j, k}


        # ── Pass C: name → price (classic, no barcode between) ─────────────
        for i, line in enumerate(lines[item_zone_start:item_zone_end], start=item_zone_start):
            if i in used:
                continue
            if not self._is_name(line):
                continue
            j = self._next_free(i + 1, n, used)
            if j is None:
                continue
            price = self._price_of(lines[j])
            if price and price > 0:
                sku, k = self._maybe_barcode(j + 1, n, used, lines)
                items.append(self._build(line.strip(), price, sku, source_idx=i))
                used |= ({i, j} | ({k} if k is not None else set()))


        # ── Pass D: inline "NAME   PRICE" ───────────────────────────────────
        for i, line in enumerate(lines[item_zone_start:item_zone_end], start=item_zone_start):
            if i in used:
                continue
            m = _PRICE_INLINE.match(line.strip())
            if not m:
                continue
            name = m.group(1).strip()
            try:
                price = float(m.group(2).replace(",", ""))
            except ValueError:
                continue
            if price <= 0 or price in skip_prices or not self._is_name(name, n, i):
                continue
            sku, k = self._maybe_barcode(i + 1, n, used, lines)
            items.append(self._build(name, price, sku, source_idx=i))
            used |= ({i} | ({k} if k is not None else set()))

        # Sort by source line index to restore receipt order
        items.sort(key=lambda x: x.get('_src', 0))
        # Strip internal _src key before returning
        for item in items:
            item.pop('_src', None)
        logger.debug(f"[Extractor] {len(items)} items found")
        return items

    # ── Item helpers ──────────────────────────────────────────────────────────

    def _collect_financial_prices(self, lines: List[str]) -> set:
        """
        Pre-scan the receipt for prices that belong ONLY to financial summary lines
        (CHANGE, AMOUNT TENDERED, CASH, etc.) so we never assign them to items.

        IMPORTANT EXCLUSION RULE:
        We do NOT add a price to skip_prices if that same price also appears
        as a TAXED price (with T/X/Z suffix) anywhere on the receipt.
        
        Why: On single-item receipts, TOTAL == item price.
          "NID05+PDR MLK2kg"
          "*BP"
          "1220.00T"     ← item price (taxed)
          "480036140523"
          "TOTAL"
          "1220.00"      ← total (same value, no T suffix)
          
        Without this guard, 1220.00 would be added to skip_prices and
        the only item would never be found.

        We ONLY skip prices that appear near these definitive non-item keywords:
        CHANGE, CASH TENDERED, AMOUNT TENDERED, TOTAL PAYMENT, TOTAL AMOUNT,
        TOTAL (only when a taxed version of the same price also exists as item).
        """
        financial_prices = set()
        n = len(lines)

        # First: collect all prices that appear as taxed item prices (with T/X/Z)
        # These are unambiguously item prices — never add to skip_prices
        taxed_prices = set()
        for line in lines:
            if self._is_taxed_price(line):
                p = self._price_of(line)
                if p:
                    taxed_prices.add(p)

        # Definitive financial-only keywords (these prices can NEVER be items)
        # Excludes plain "TOTAL" because total == item price on single-item receipts
        _DEFINITIVE_FINANCIAL = re.compile(
            r'^(CHANGE|CASH\s+TENDERED|AMOUNT\s+TENDERED|TOTAL\s+PAYMENT|'
            r'TOTAL\s+AMOUNT|NET\s+AMOUNT|AMOUNT\s+DUE|GRAND\s+TOTAL|'
            r'CASH|TOTAL\s+SALES)\s*[:\-]?\s*$',
            re.IGNORECASE
        )

        for i, line in enumerate(lines):
            s = line.strip()
            norm = _normalize_for_skip(s)

            is_definitive = bool(_DEFINITIVE_FINANCIAL.match(s))
            is_mercury_junk = bool(_MERCURY_JUNK.search(s))

            if is_definitive or is_mercury_junk:
                # Inline price on same line
                m = re.search(r'[₱P]?\s*([\d,]+\.\d{2})', s)
                if m:
                    try:
                        p = float(m.group(1).replace(',', ''))
                        if p not in taxed_prices:
                            financial_prices.add(p)
                    except ValueError:
                        pass

                # Price on next line
                if i + 1 < n:
                    p = self._price_of(lines[i + 1])
                    if p and p > 0 and p not in taxed_prices:
                        financial_prices.add(p)

                # Price on previous line
                if i > 0:
                    p = self._price_of(lines[i - 1])
                    if p and p > 0 and p not in taxed_prices:
                        financial_prices.add(p)

        logger.debug(f"[Extractor] Taxed item prices: {taxed_prices}")
        logger.debug(f"[Extractor] Financial price exclusions: {financial_prices}")
        return financial_prices

    def _is_qty_line(self, line: str) -> bool:
        """
        Returns True if this line is a Mercury Drug quantity×unit-price line.
        e.g. "3 @ 36.00" or "10 @ 6.75"
        
        These lines appear between an item name and its barcode.
        When OCR merges columns they collapse to "336.00" or "106.75" — numbers
        that look exactly like valid prices but are NOT the item price.
        
        We detect them in their pre-merged form. The merged form (336.00) is
        handled separately in _collect_financial_prices via the context guard.
        """
        return bool(_QTY_AT_PRICE.match(line.strip()))

    def _price_of(self, line: str) -> Optional[float]:
        s = line.strip()
        # Qty lines "3 @ 36.00" must never be treated as prices
        if self._is_qty_line(s):
            return None
        m = _PRICE_ONLY.match(s)
        if not m:
            return None
        try:
            return float(m.group(1).replace(',', ''))
        except ValueError:
            return None

    def _is_barcode(self, line: str) -> bool:
        return bool(_BARCODE.match(line.strip()))

    def _is_taxed_price(self, line: str) -> bool:
        """
        Returns True if this line is a price with a Mercury Drug taxability suffix.
        e.g. "108.00T" "499.50T" "1310.00T"  (T=taxable, X=exempt, Z=zero-rated)
        
        Why this matters for Pass A:
        Mercury Drug prints item prices with T/X/Z suffix.
        Qty×unit-price collapsed lines like "336.00" have NO suffix.
        Using this distinction in Pass A prevents qty lines from acting as prices.
        """
        s = line.strip()
        return bool(re.match(r'^[₱P]?\s*[\d,]+\.\d{2}[TXZ]$', s))

    def _is_name(self, line: str, total_lines: int = 0, line_idx: int = 0) -> bool:
        """
        Determine if a line is a product name.

        Two-stage approach:
        Stage 1 — Hard rejects (always skip regardless of anything):
          - Looks like a price, barcode, separator, or pure digits
          - Matches the PA#99 S/S Mercury Drug prescription indicator
          - Matches _FINANCIAL_LINE pattern exactly (the definitive financial lines)

        Stage 2 — Smart keyword check (replaces the old blunt _SKIP_ITEM check):
          The old check skipped ANY line containing a financial keyword.
          That caused real products like "NET WT 1.5KG CHICKEN" to be skipped
          because NET is in the keyword list.

          New logic:
          a) Normalize the line for OCR confusions (0→O, 1→I) and re-check
             _SKIP_ITEM. This catches "T0TAL" and "TOTAI" misreads.
          b) If keyword found on NORMALIZED text AND line has NO product indicators
             (units like ML/KG/G, or alphanumeric product codes) → skip.
          c) If keyword found BUT line HAS product indicators → it's a real item,
             pass it through (e.g. "NET WT 1.5KG CHICKEN" has "1.5KG" → pass).
          d) Position heuristic (optional): financial lines are almost always in
             the bottom 25% of the receipt. If a line triggers keyword match AND
             is in the bottom 25% → skip with more confidence.
        """
        s = line.strip()

        # Stage 1: Hard rejects
        if len(s) < 2:
            return False
        if self._price_of(s) is not None:
            return False
        if self._is_barcode(s):
            return False
        if _QTY_LINE.match(s):           # "4 @ 299.00", "84 @ 16.50" — qty×price lines
            return False
        if _PA_MODE.match(s):
            return False
        if _SEPARATOR.match(s):
            return False
        if re.match(r'^\d+$', s):
            return False
        if _FINANCIAL_LINE.match(s):   # definitive financial line patterns
            return False
        if _MERCURY_JUNK.search(s):     # *BP, (T), LESSBPDISC, etc.
            return False
        if _PAYMENT_METHOD.match(s):    # CRED CRD, GCASH, PAYMAYA, VISA, etc.
            return False
        if _METADATA_JUNK.search(s):   # machine IDs, Phillogix, PTU, Approval#, etc.
            return False
        # Explicit guard: "VAT12%" "TAX5%" "VAT-12%" — financial keyword + percent
        # These don't match _SKIP_ITEM because  doesn't fire before digits.
        if re.match(r'^(VAT|TAX|DISC|DISCOUNT)\s*[-–]?\s*\d+\s*%', s, re.IGNORECASE):
            return False
        # "LESS : BP DISC 5% x 1220.00" — LESS + percentage discount lines
        if re.match(r'^LESS', s, re.IGNORECASE) and '%' in s:
            return False

        # Stage 2: Smart keyword check with product-indicator rescue
        normalized = _normalize_for_skip(s)

        # Check keyword on normalized text (catches OCR misreads like T0TAL, TOTAI)
        if _SKIP_ITEM.search(normalized):
            # Keyword found — but is this actually a product?
            has_unit = bool(_PRODUCT_UNITS.search(s))
            has_code = bool(_PRODUCT_CODE.search(s))

            # Product indicators: measurement units OR alphanumeric product codes
            has_product_signal = has_unit or has_code

            if not has_product_signal:
                # No product signals → financial/noise line, skip it
                return False

            # Has product signals but also has a financial keyword.
            # Apply position heuristic: if in bottom 25% of receipt → skip.
            # Financial summary block is always at the bottom.
            if total_lines > 8 and line_idx > 0:
                position_ratio = line_idx / total_lines
                if position_ratio > 0.75:
                    return False   # bottom 25%: financial keyword + bottom position = skip

            # Has product signal AND not in the financial zone → it's a real item
            return True

        return True

    def _next_free(self, start: int, n: int, used: set) -> Optional[int]:
        for idx in range(start, n):
            if idx not in used:
                return idx
        return None

    def _next_price(self, start: int, n: int, used: set, lines: List[str],
                    max_skip: int = 3) -> Optional[int]:
        """
        Like _next_free but skips known junk lines to find the next price line.

        Why needed:
          Mercury Drug inserts discount/flag markers BETWEEN an item name
          and its price, e.g.:
            "NID05+PDR MLK2kg"   ← name
            "*BP"                ← blood pressure discount marker (junk)
            "1220.00T"           ← actual price

          _next_free() returns "*BP" which is not a price, so Pass C fails.
          _next_price() skips junk lines (MERCURY_JUNK, separators, PA lines)
          and returns the index of the actual price line.

        max_skip: how many junk lines to skip before giving up (prevents
                  accidentally jumping over a real price gap).
        """
        skipped = 0
        for idx in range(start, n):
            if idx in used:
                continue
            s = lines[idx].strip()
            # Is this line a price? Return it.
            if self._price_of(s) is not None:
                return idx
            # Is this line skippable junk? Count and continue.
            is_junk = (
                bool(_MERCURY_JUNK.search(s))
                or bool(_SEPARATOR.match(s))
                or bool(_PA_MODE.match(s))
                or bool(_PAYMENT_METHOD.match(s))
                or len(s) <= 2          # lone punctuation like ":" or "."
            )
            if is_junk:
                skipped += 1
                if skipped >= max_skip:
                    return None
                continue
            # Not a price, not junk → real content, stop searching
            return None
        return None

    def _has_price_before(self, lines, name_idx: int, used: set) -> bool:
        """Return True if an unused price-only line immediately precedes name_idx."""
        for back in range(name_idx - 1, -1, -1):
            if back in used:
                continue
            s = lines[back].strip()
            if self._is_barcode(s):
                continue
            if self._price_of(s) is not None:
                return True
            break
        return False

    def _maybe_barcode(self, start: int, n: int, used: set, lines: List[str]):
        """Return (sku_string, index) if the next free line is a barcode, else (None, None)."""
        k = self._next_free(start, n, used)
        if k is not None and self._is_barcode(lines[k]):
            return lines[k].strip(), k
        return None, None

    def _build(self, name: str, price: float, sku: Optional[str],
                qty: Optional[int] = None, unit_price: Optional[float] = None,
                source_idx: int = 0) -> Dict:
        """
        Build a standardized item dict.

        qty / unit_price populated either from the name itself ("2x ITEM")
        or from an explicit qty line ("84 @ 16.50") passed in by the caller.
        """
        clean = name
        inferred_qty = 1
        # qty prefix: "2x ITEM" or "2 x ITEM"
        m = re.match(r'^(\d+)\s*[xX]\s+(.+)$', clean)
        if m:
            inferred_qty = int(m.group(1))
            clean = m.group(2).strip()
        # qty suffix: "ITEM x2"
        m2 = re.match(r'^(.+?)\s+[xX](\d+)\s*$', clean)
        if m2:
            clean = m2.group(1).strip()
            inferred_qty = int(m2.group(2))

        final_qty        = qty if qty is not None else inferred_qty
        final_unit_price = unit_price  # None if not a multi-qty item

        return {
            'name':       clean,
            'price':      round(price, 2),
            'qty':        final_qty,
            'unit_price': final_unit_price,
            'sku':        sku,
            '_src':       source_idx,   # receipt line index — used for sort, stripped before return
        }

    def _parse_qty_line(self, line: str):
        """
        Parse a quantity line like "4 @ 299.00" or "84 @ 16.50".
        Returns (qty, unit_price) or (None, None).
        """
        m = _QTY_LINE.match(line.strip())
        if m:
            try:
                return int(m.group(1)), float(m.group(2).replace(',', ''))
            except ValueError:
                pass
        return None, None

    def _stated_item_count(self, lines: List[str]) -> Optional[int]:
        """
        Parse the receipt's own stated item count. Handles two formats:

        Inline (all on one line):
          "** 2 item(s) **"   → 2
          "** 16 items **"    → 16
          "* 6 item(s) *"     → 6

        Split (OCR breaks it across lines):
          "**"
          "1item(s)"          ← number and word together, no stars
          "**"

        The split format appears when OCR treats the two ** columns
        as separate text boxes.
        """
        n = len(lines)

        # Pass 1: inline format
        for line in lines:
            m = _ITEM_COUNT_LINE.search(line)
            if m:
                try:
                    count = int(m.group(1))
                    logger.debug(f"[Extractor] Stated item count (inline): {count}")
                    return count
                except (ValueError, IndexError):
                    pass

        # Pass 2: split format — bare "Nitem(s)" line between "**" lines
        _BARE_COUNT = re.compile(r'^(\d+)\s*item(?:s|\(s\))?$', re.IGNORECASE)

        # Pass 3: "ITEMS PURCHASED : N" or "ITEMS PURCHASEO : N" (SM supermarket)
        _ITEMS_PURCHASED = re.compile(
            r'ITEMS?\s+PURCHAS(?:ED|EO|E)\s*[:#]?\s*(\d+)', re.IGNORECASE
        )
        for i, line in enumerate(lines):
            m = _BARE_COUNT.match(line.strip())
            if m:
                # Check that surrounding lines are "**" separators
                prev_ok = (i > 0 and lines[i-1].strip() in ('**', '*', '***'))
                next_ok = (i + 1 < n and lines[i+1].strip() in ('**', '*', '***'))
                if prev_ok or next_ok:
                    try:
                        count = int(m.group(1))
                        logger.debug(f"[Extractor] Stated item count (split): {count}")
                        return count
                    except (ValueError, IndexError):
                        pass

        # Pass 3: "ITEMS PURCHASED : N" (SM Supermarket format)
        for line in lines:
            m = _ITEMS_PURCHASED.search(line)
            if m:
                try:
                    count = int(m.group(1))
                    logger.debug(f"[Extractor] Stated item count (purchased): {count}")
                    return count
                except (ValueError, IndexError):
                    pass
        return None

    def _validate_items(
        self,
        items: List[Dict],
        total_amount: Optional[str],
        stated_count: Optional[int],
    ) -> List[Dict]:
        """
        Post-extraction sanity checks to remove false-positive items.

        Check 1 — Price sum vs total:
          Sum all item prices. If sum is significantly MORE than the receipt
          total, we have fake items inflating the sum. Remove the item whose
          price, when subtracted, brings the sum closest to the real total.
          Repeat until sum ≈ total or no more removable items.
          Tolerance: 1% of total (covers minor rounding / discount lines).

        Check 2 — Stated item count cap:
          Receipt explicitly says "** N item(s) **". If we found more than N,
          remove extras with lowest confidence (prefer items with barcodes,
          prefer items with T/X/Z-suffixed prices, remove items whose name
          looks like a payment method or metadata line).

        We apply Check 1 first because it uses hard numeric evidence.
        Check 2 is a secondary guard.
        """
        if not items:
            return items

        # Parse total as float
        total_float = None
        if total_amount:
            try:
                total_float = float(total_amount.replace('₱', '').replace(',', ''))
            except ValueError:
                pass

        # NOTE: Price-sum validation intentionally removed.
        # Receipts with discounts (BP DISC, SC DISC, PWD, promos) have
        # item prices that legitimately exceed the final total. Checking
        # sum == total would incorrectly remove real items in those cases.

        # ── Check 2: stated item count cap ───────────────────────────────────
        if stated_count and len(items) > stated_count:
            # Remove items without SKUs first (payment lines rarely have barcodes)
            no_sku = [i for i in items if not i['sku']]
            with_sku = [i for i in items if i['sku']]

            # Sort no-sku items: remove ones whose names look most like metadata
            def removal_priority(item):
                name = item['name'].upper()
                # Higher score = remove first
                score = 0
                if not item['sku']: score += 10
                if len(name) <= 6: score += 5        # short names = likely metadata
                if any(c in name for c in ['#', ':', '*']): score += 8
                return score

            items_sorted = sorted(items, key=removal_priority, reverse=True)
            items = items_sorted[:stated_count]
            logger.info(
                f"[Extractor] Capped items to stated count {stated_count}: "
                f"{[i['name'] for i in items]}"
            )

        return items

    @staticmethod
    def _empty() -> Dict:
        return {
            'store_name': None, 'invoice_number': None, 'date': None,
            'time': None, 'total_amount': None, 'vat_amount': None,
            'tin': None, 'item_count': 0, 'has_vat': False, 'items': [],
        }


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import json

    mercury_lines = [
        "MERCURY DRUG - RIZAL BANANGONAN EM COMPLEX",
        "EM Comp ex, Mani la East Road,",
        "Brgy.Pantok,Binangonan, R1za",
        "VAT REG TIN : 000-388-474-00778",
        "TN0(02650-605",
        "MOBILE/VTBER NO : 0908813-2818",
        "TOSHIBA4900 41CRD20R003 01070",
        "MIN23051210390080104[1.5.30]31",
        "PA99S/S",
        "1220.00T",
        "NIDO5+PDR MLK2kg",
        "480036140523",
        "90.00T",
        "GREEN COF MX219",
        "518.00",
        "480901464106",
        "TOTAL",
        "1310.00",
        "AMOUNT TENDERED",
        "CASH",
        "2000.00",
        "TOTAL PAYMENT",
        "2000.00",
        "CHANGE",
        "690.00",
        "** 6 item(s) **",
        "VATAble (T)  1169.64",
        "VAT-Exempt Sale (X)  0.00",
        "VAT Zero-Rated Sale(Z)  0.00",
        "VAT - 12%  140.36",
        "Amount Due  1310.00",
        "TXN#110855 11-13-25 02:15P EJ",
        "INVOICE#110703137533",
        "- THIS IS YOUR INVOICE -",
    ]

    e = GeneralMetadataExtractor()
    r = e.extract(mercury_lines)
    print(json.dumps(r, indent=2, ensure_ascii=False))

    assert r['store_name'] == "MERCURY DRUG - RIZAL BANANGONAN EM COMPLEX"
    assert r['invoice_number'] == "110703137533"
    assert r['date'] == "11-13-25"
    assert r['time'] is not None and "02:15" in r['time']
    assert r['total_amount'] == "₱1,310.00"
    assert r['vat_amount'] == "₱140.36"
    assert r['tin'] == "000-388-474-00778"
    assert len(r['items']) >= 2
    nido = next(x for x in r['items'] if 'NIDO' in x['name'])
    assert nido['price'] == 1220.0
    assert nido['sku'] == '480036140523'
    print("\n✅ ALL ASSERTIONS PASSED")