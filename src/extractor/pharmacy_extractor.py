"""
Pharmacy Column Extractor
=========================
Handles Mercury Drug, Rose Pharmacy, Generika, Watsons, South Star Drug —
any pharmacy that uses the two-column OCR layout where the price column
is read BEFORE the item name column.
"""

import re
from typing import List, Dict, Optional, Set, Tuple

from extractor.base_extractor import BaseExtractor
from loguru import logger


# ─── Patterns specific to pharmacy layout ─────────────────────────────────────

_BARCODE = re.compile(r'^\d{6,14}$')
_SEPARATOR = re.compile(r'^[\-\*\=\s\.]+$|^\*\*.*\*\*$')
_PRICE_ONLY = re.compile(r'^\s*[₱P]?\s*([\d,]+\.\d{1,2})\s*[TXZVvy]?\s*$')
_PRICE_INLINE = re.compile(r'^(.+?)\s{2,}[₱P]?\s*([\d,]+\.\d{2})[TXZ]?\s*$')

_QTY_LINE = re.compile(r'^(\d{1,4})\s*[@xX×]\s*([\d,]+\.\d{2})\s*$')
_QTY_AT_PRICE = re.compile(
    r'^\d+\s*@\s*[\d,]+\.\d{2}$'
    r'|\d+\s+@\s+[\d,]+\.\d{2}$'
)

_PA_MODE = re.compile(
    r'^PA\s*#?\s*\d+\s*S/S$'
    r'|^PA\s*#?\s*\d+\s*\w{0,8}$'
    r'|^PA\s*#\s*\d+\s+[A-Za-z][A-Za-z-]{0,12}$',
    re.IGNORECASE,
)

_MERCURY_JUNK = re.compile(
    r'^\*[A-Z]{1,4}$'
    r'|^\([TXZSE]\)$'
    r'|LESS\s*:?\s*BP\s*DISC'
    r'|LESSBPDISC'
    r'|^LESS\b.*\bDISC\b'
    r'|^\*{1,2}[A-Z0-9\s]{1,6}\*{0,2}$'
    r'|^[\(\[][TXZSEPWDB]{1,3}[\)\]]$',
    re.IGNORECASE,
)

_PAYMENT_METHOD = re.compile(
    r'^(CRED\s*CRD|CRED\s*CARD|DEBIT\s*CRD|DEBIT\s*CARD|'
    r'GCASH|G\s*CASH|PAYMAYA|MAYA|PAYPAL|'
    r'UNIONPAY|VISA|MASTERCARD|AMEX|JCB|'
    r'BDO|BPI|METROBANK|CHINABANK|RCBC|PNB|LANDBANK|DBP|'
    r'CHECK|CHEQUE|VOUCHER|E\s*WALLET|EWALLET|'
    r'APPROVAL|APPROVAL\s*#|ORDER\s*#|CARD\s*#|'
    r'SOLD\s*TO|SOLDTO|PAYMAYA|SUKI\s*#|NAME\s*:)'
    r'.*$'
    r'|^MEMBER\s+N[AO](?:NE|ME|)\b'
    r'|^ITEMS?\s+PURCHAS'
    r'|^VAT(?:ABLE|EBLE|ABLE|EABLE)?\s*SALE'
    r'|^VAT(?:\s*EXEMPT|\s*ZERO|\s*\()'
    r'|^ZERO\s+RATED\s+SALE'
    r'|^VAT\s+EXEMPT\s+SALE'
    r'|^(NANE|NANS|NAME|ADDRESS|TIN|BUSINESS\s*STYLE)\s*:\s*$',
    re.IGNORECASE,
)

_METADATA_JUNK = re.compile(
    r'^(TOSHIBA|POSTEK|EPSON|CASIO|NCR|SAMSUNG)\b'
    r'|^MIN\d{10,}'
    r'|\[\d+\.\d+\.\d+\]'
    r'|^Phillogix'
    r'|^433\s*Lt\.?\s*Artiaga'
    r'|^PTU\s*No\.?'
    r'|^Accred\s*No'
    r'|^VAT\s*REG\s*TIN\s*\d'
    r'|^Approva[l1]\s*#'
    r'|^Card\s*#\s*\*+'
    r'|^PWDID\s*#'
    r'|^SUKI\s*#'
    r'|^NAME\s*:.*\*'
    r'|^(SIGNATURE|SOLD\s*TO|ADDRESS|TIN\s*NO|BUSINES\s*STYLE)\s*:?\s*_{0,}$'
    r'|^-{5,}$'
    r'|^={5,}$'
    r'|^NAME[\:\s].*\*{3,}'
    r'|^SN#\S+'
    r'|^Vincor\s+Nixdorf'
    r'|^SALESINVOICE\d'
    r'|^\d{9,}[A-Z]{2,}'
    r'|^[A-Z]\d{2,}[A-Z]\d+[A-Z]\d+'
    r'|^O\s+Lite\s*$',
    re.IGNORECASE,
)

_SKIP_ITEM = re.compile(
    r'\b(TOTAL|SUBTOTAL|CHANGE|CASH|CARD|PAYMENT|TENDERED|DISCOUNT|LESS|'
    r'VAT|TAX|BALANCE|DUE|PAID|AMOUNT|VOID|REFUND|TIN|DATE|TIME|CASHIER|'
    r'THANK|WELCOME|PLEASE|COME|AGAIN|SAVE|SENIOR|PWD|MEMBER|POINTS|LOYALTY|'
    r'DEBIT|CREDIT|NET|GROSS|INVOICE|INVOI|SOLD|ADDRESS|VATAble|Exempt|Zero|Rated|'
    r'Phillogix|Accred|PTU|MIN|TXN|TOSHIBA|MOBILE|VIBER|BRGY|BARANGAY|'
    r'RECEIPT|YOUR|THIS|MERCHANDISE|CONDITION|SALAMAT|MARAMING|LAGING|'
    r'NAKASISIGURO|GAMOT|BAGO|SUKI|items?)\b',
    re.IGNORECASE,
)

_FINANCIAL_LINE = re.compile(
    r'^(SUBTOTAL|SUBTOIAL|SUBT0TAL|SUB\s*TOTAL|GRAND\s*TOTAL|'
    r'TOTAL\s*AMOUNT|AMOUNT\s*DUE|'
    r'TOTAL\s*PAYMENT|TOTAL\s*SALES|NET\s*AMOUNT|NET\s*SALES|'
    r'CASH\s*TENDERED|AMOUNT\s*TENDERED|TOTAL\s*TENDERED|'
    r'CHANGE|CHANG3|CH4NGE|BALANCE|CASH|DEBIT|CREDIT|VAT|TAX|DISCOUNT|'
    r'VATABLE|VAT[\s\-]*EXEMPT|ZERO[\s\-]*RATED|OUTPUT\s*TAX|'
    r'TOTAL|TOTAI|T0TAL|T0TAI|T0TALS?|VAT\s*[-–]?\s*\d+%?)\s*[:\-₱P\d\.]*\s*$',
    re.IGNORECASE,
)

_PRODUCT_UNITS = re.compile(
    r'(\d+\.?\d*\s*(?:ML|L|KG|G|MG|PCS|PC|TAB|CAP|TABS|CAPS|BOX|BTL|PKT|PCK|'
    r'SACHET|POUCH|ROLL|PAIR|SET|SHEET|BAG|CAN|JAR|TUB|TUBE|OZ|LB|GM|GMS|KCAL|MCG|IU)'
    r'|(?<![A-Za-z])(?:ML|KG|MG|PCS|TAB|TABS|CAPS|CAP|BOX|BTL|PKT|PCK|SACHET|POUCH|'
    r'ROLL|PAIR|SET|BAG|CAN|JAR|TUB|TUBE|OZ|LB|GM|GMS)(?![A-Za-z]))',
    re.IGNORECASE,
)

_PRODUCT_CODE = re.compile(
    r'(?<![A-Za-z])([A-Z]{2,}\d+|\d+[A-Z]{2,})(?![A-Za-z%])',
    re.IGNORECASE,
)

_ITEM_COUNT_LINE = re.compile(
    r'\*+\s*(\d+)\s*item(?:s|\(s\))?\s*\**',
    re.IGNORECASE,
)

_ZONE_END = re.compile(
    r'^(SUBTOTAL|SUB\s*TOTAL|GRAND\s*TOTAL|CHANGE|CHANGE\s*DUE|'
    r'AMOUNT\s*TENDERED|CASH\s*TENDERED|TOTAL\s*PAYMENT)\s*[:\-]?\s*$',
    re.IGNORECASE,
)

_ZONE_START_EXTRA = re.compile(r'^PHP\s*$', re.IGNORECASE)

_BP_DISC_PRICE = re.compile(
    r'(?:LESS|BPDISC|BP\s*DISC)[^x×X]*[x×X]\s*([\d,]+\.?\d{0,2})',
    re.IGNORECASE,
)

_DEFINITIVE_FINANCIAL = re.compile(
    r'^(CHANGE|CASH\s+TENDERED|AMOUNT\s+TENDERED|TOTAL\s+PAYMENT|'
    r'TOTAL\s+AMOUNT|NET\s+AMOUNT|AMOUNT\s+DUE|GRAND\s+TOTAL|'
    r'CASH|TOTAL\s+SALES)\s*[:\-]?\s*$',
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    t = text.upper()
    return t.replace('0', 'O').replace('1', 'I').replace('|', 'I').replace('5', 'S')


class PharmacyColumnExtractor(BaseExtractor):
    """
    Extractor for two-column pharmacy receipts.
    Inherits all shared field logic from BaseExtractor.
    Only _items() is specific to this layout.
    """

    def _items(self, lines: List[str]) -> List[Dict]:
        n = len(lines)
        used: Set[int] = set()
        items: List[Dict] = []

        # ── Item zone boundaries ──────────────────────────────────────────────
        item_zone_start = 0
        item_zone_end   = n

        for idx, line in enumerate(lines):
            s = line.strip()
            if item_zone_start == 0 and (
                _PA_MODE.match(s) or _ZONE_START_EXTRA.match(s)
            ):
                used.add(idx)
                _HEADER_LINE = re.compile(
                    r'^(VAT\s+REG\s+TIN|TEL\s*NO|MOBILE|TOSHIBA|MTN:|MIN\d|'
                    r'VIBER|Brgy\.|Barangay|MOBILE/VIBER|IBM\d|'
                    r'\d{3}-\d{3}-\d{3})',
                    re.IGNORECASE
                )
                zone_back = idx
                for back in range(idx - 1, -1, -1):
                    bs = lines[back].strip()
                    if not bs:
                        continue
                    if _HEADER_LINE.search(bs):
                        break
                    if _SEPARATOR.match(bs):
                        break
                    if self._is_name(bs, n, back):
                        zone_back = back
                    if idx - back > 6:
                        break
                item_zone_start = zone_back
            if item_zone_start > 0 and idx > item_zone_start and _ZONE_END.match(s):
                item_zone_end = idx
                break

        skip_prices = self._collect_financial_prices(lines)

        # ── Pass B2: name → barcode → qty_line → price ────────────────────────
        for i in range(item_zone_start, item_zone_end):
            if i in used or not self._is_name(lines[i], n, i):
                continue
            j = i + 1
            if j >= n or j in used or not self._is_barcode(lines[j]):
                continue
            k = j + 1
            if k >= n or k in used:
                continue
            qty, unit_price = self._parse_qty_line(lines[k])
            if qty is None:
                continue
            m_idx = k + 1
            if m_idx >= n or m_idx in used:
                continue
            price = self._price_of(lines[m_idx])
            if price and price > 0 and price not in skip_prices:
                items.append(self._build_item(
                    lines[i].strip(), price, lines[j].strip(),
                    qty=qty, unit_price=unit_price, source_idx=i,
                ))
                used |= {i, j, k, m_idx}

        # ── Pass A1b: name → [junk] → price ──────────────────────────────────
        for i in range(item_zone_start, item_zone_end):
            if i in used or not self._is_name(lines[i], n, i):
                continue
            j = self._next_price(i + 1, n, used, lines, max_skip=3)
            if j is None:
                continue
            price = self._price_of(lines[j])
            if price is None or price <= 0 or price in skip_prices:
                continue
            is_taxed = self._is_taxed_price(lines[j])
            junk_indices: Set[int] = set(
                k for k in range(i + 1, j) if k not in used
            )
            has_junk = bool(junk_indices)
            sku, m = self._maybe_barcode(j + 1, n, used, lines)
            qty_a1b, unit_a1b, q_idx_a1b = None, None, None
            if m is not None:
                q_next = self._next_free(m + 1, n, used)
                if q_next is not None:
                    _qty, _unit = self._parse_qty_line(lines[q_next])
                    if _qty is not None:
                        qty_a1b, unit_a1b, q_idx_a1b = _qty, _unit, q_next
            if is_taxed or sku is not None or has_junk:
                items.append(self._build_item(
                    lines[i].strip(), price, sku,
                    qty=qty_a1b, unit_price=unit_a1b, source_idx=i,
                ))
                used |= (
                    {i, j} | junk_indices
                    | ({m} if m is not None else set())
                    | ({q_idx_a1b} if q_idx_a1b is not None else set())
                )

        # ── Pass A1a: price → name (→ barcode) ───────────────────────────────
        for i in range(item_zone_start, item_zone_end):
            if i in used or not self._is_taxed_price(lines[i]):
                continue
            price = self._price_of(lines[i])
            if price is None or price <= 0 or price in skip_prices:
                continue
            skip = False
            for back in range(1, 4):
                bi = i - back
                if bi < item_zone_start or bi in used:
                    break
                bs = lines[bi].strip()
                if self._is_barcode(bs):
                    ni = bi - 1
                    while ni >= item_zone_start and ni in used:
                        ni -= 1
                    if ni >= item_zone_start and self._is_name(lines[ni], n, ni):
                        skip = True
                    break
                if _QTY_LINE.match(bs):
                    continue
                if not _MERCURY_JUNK.search(bs) and not _SEPARATOR.match(bs):
                    break
            if skip:
                continue
            j = self._next_free(i + 1, n, used)
            if j is not None and self._is_name(lines[j], n, j):
                qty, unit_price, q_idx = None, None, None
                after_name = self._next_free(j + 1, n, used)
                if after_name is not None:
                    _qty, _unit = self._parse_qty_line(lines[after_name])
                    if _qty is not None:
                        qty, unit_price, q_idx = _qty, _unit, after_name
                barcode_start = q_idx + 1 if q_idx is not None else j + 1
                sku, k = self._maybe_barcode(barcode_start, n, used, lines)
                items.append(self._build_item(
                    lines[j].strip(), price, sku,
                    qty=qty, unit_price=unit_price, source_idx=j
                ))
                used |= ({i, j}
                         | ({q_idx} if q_idx is not None else set())
                         | ({k} if k is not None else set()))

        # ── Pass A2: untaxed price → name ────────────────────────────────────
        for i in range(item_zone_start, item_zone_end):
            if i in used or self._is_taxed_price(lines[i]):
                continue
            price = self._price_of(lines[i])
            if price is None or price <= 0 or price in skip_prices:
                continue
            j = self._next_free(i + 1, n, used)
            if j is None or not self._is_name(lines[j], n, j):
                continue
            k_after = self._next_free(j + 1, n, used)
            if k_after is not None:
                np_ = self._price_of(lines[k_after])
                if np_ and np_ > 0 and np_ not in skip_prices:
                    continue
            sku, k = self._maybe_barcode(j + 1, n, used, lines)
            items.append(self._build_item(lines[j].strip(), price, sku, source_idx=j))
            used |= ({i, j} | ({k} if k is not None else set()))

        # ── Pass B: name → [junk/qty_line] → barcode → price ────────────────
        _TOTAL_LBL = re.compile(
            r'^(TOTAL|SUB\s*TOTAL|GRAND\s*TOTAL)\s*[:\-\.]?\s*$', re.IGNORECASE
        )
        for i in range(item_zone_start, item_zone_end):
            if i in used or not self._is_name(lines[i], n, i):
                continue
            if self._has_price_before(lines, i, used, item_zone_start):
                continue
            barcode_idx = None
            junk_b: Set[int] = set()
            qty_b, unit_b, qty_idx_b = None, None, None
            for scan in range(i + 1, min(i + 6, n)):
                if scan in used:
                    break
                s_scan = lines[scan].strip()
                if self._is_barcode(s_scan):
                    barcode_idx = scan
                    break
                _q, _u = self._parse_qty_line(s_scan)
                if _q is not None:
                    qty_b, unit_b, qty_idx_b = _q, _u, scan
                    junk_b.add(scan)
                    continue
                is_j = (
                    bool(_MERCURY_JUNK.search(s_scan))
                    or bool(_SEPARATOR.match(s_scan))
                    or bool(re.match(r'^\d{3,5}$', s_scan))
                    or len(s_scan) <= 2
                )
                if is_j:
                    junk_b.add(scan)
                else:
                    break
            if barcode_idx is None:
                continue
            k = barcode_idx + 1
            price = self._price_of(lines[k]) if (k < n and k not in used) else None
            price_is_total = (
                price is not None and k + 1 < n
                and bool(_TOTAL_LBL.match(lines[k + 1].strip()))
            )
            if price_is_total and qty_b is not None and unit_b is not None:
                derived = round(qty_b * unit_b, 2)
                items.append(self._build_item(
                    lines[i].strip(), derived, lines[barcode_idx].strip(),
                    qty=qty_b, unit_price=unit_b, source_idx=i
                ))
                used |= ({i, barcode_idx} | junk_b)
            elif price_is_total and qty_b is None and price and price > 0 and price not in skip_prices:
                items.append(self._build_item(
                    lines[i].strip(), price, lines[barcode_idx].strip(),
                    source_idx=i
                ))
                used |= ({i, barcode_idx, k} | junk_b)
            elif price and price > 0 and price not in skip_prices and not price_is_total:
                items.append(self._build_item(
                    lines[i].strip(), price, lines[barcode_idx].strip(),
                    qty=qty_b, unit_price=unit_b, source_idx=i
                ))
                used |= ({i, barcode_idx, k} | junk_b)
            elif price is None and junk_b:
                recovered = self._bp_disc_price_in_zone(lines, 0, n)
                if recovered and recovered > 0:
                    items.append(self._build_item(
                        lines[i].strip(), recovered, lines[barcode_idx].strip(), source_idx=i
                    ))
                    used |= ({i, barcode_idx} | junk_b)

        # ── Pass C: name → price (→ barcode) ─────────────────────────────────
        for i in range(item_zone_start, item_zone_end):
            if i in used or not self._is_name(lines[i]):
                continue
            j = self._next_free(i + 1, n, used)
            if j is None:
                continue
            price = self._price_of(lines[j])
            if price and price > 0:
                sku, k = self._maybe_barcode(j + 1, n, used, lines)
                qty, unit_price, q_idx = None, None, None
                if k is not None:
                    q_next = self._next_free(k + 1, n, used)
                    if q_next is not None:
                        _qty, _unit = self._parse_qty_line(lines[q_next])
                        if _qty is not None:
                            qty, unit_price, q_idx = _qty, _unit, q_next
                items.append(self._build_item(
                    lines[i].strip(), price, sku,
                    qty=qty, unit_price=unit_price, source_idx=i,
                ))
                used |= (
                    {i, j}
                    | ({k} if k is not None else set())
                    | ({q_idx} if q_idx is not None else set())
                )

        # ── Pass D: inline "NAME   PRICE" ────────────────────────────────────
        for i in range(item_zone_start, item_zone_end):
            if i in used:
                continue
            m_inline = _PRICE_INLINE.match(lines[i].strip())
            if not m_inline:
                continue
            name = m_inline.group(1).strip()
            try:
                price = float(m_inline.group(2).replace(",", ""))
            except ValueError:
                continue
            if price <= 0 or price in skip_prices or not self._is_name(name, n, i):
                continue
            sku, k = self._maybe_barcode(i + 1, n, used, lines)
            items.append(self._build_item(name, price, sku, source_idx=i))
            used |= ({i} | ({k} if k is not None else set()))

        items.sort(key=lambda x: x.get("_src", 0))
        for item in items:
            item.pop("_src", None)

        items = self._infer_orphan(items, lines, used, item_zone_start, item_zone_end, n)

        stated = self._stated_item_count(lines)
        if stated and len(items) > stated:
            items = self._cap_to_stated(items, stated)

        logger.debug(f"[PharmacyColumnExtractor] {len(items)} items found")
        return items

    # ── Pharmacy-specific helpers ─────────────────────────────────────────────

    def _collect_financial_prices(self, lines: List[str]) -> set:
        financial: set = set()
        n = len(lines)
        taxed: set = set()
        for line in lines:
            if self._is_taxed_price(line):
                p = self._price_of(line)
                if p:
                    taxed.add(p)

        for i, line in enumerate(lines):
            s = line.strip()
            if _DEFINITIVE_FINANCIAL.match(s) or _MERCURY_JUNK.search(s):
                m = re.search(r'[₱P]?\s*([\d,]+\.\d{2})', s)
                if m:
                    try:
                        p = float(m.group(1).replace(',', ''))
                        if p not in taxed:
                            financial.add(p)
                    except ValueError:
                        pass
                for offset in (-1, 1):
                    idx = i + offset
                    if 0 <= idx < n:
                        p = self._price_of(lines[idx])
                        if p and p > 0 and p not in taxed:
                            financial.add(p)
        return financial

    def _is_barcode(self, line: str) -> bool:
        return bool(_BARCODE.match(line.strip()))

    def _is_taxed_price(self, line: str) -> bool:
        return bool(re.match(r'^[₱P]?\s*[\d,]+\.\d{2}[TXZ]$', line.strip()))

    def _is_name(self, line, total_lines: int = 0, line_idx: int = 0) -> bool:
        s = line.strip() if isinstance(line, str) else line
        if len(s) < 2:
            return False
        if self._price_of(s) is not None:
            return False
        if self._is_barcode(s):
            return False
        # FIX: Address / door number fragments: "1-608", "14-B", "2A"
        # These appear when OCR splits a crumpled receipt address header onto
        # its own line. Pattern: ≤8 chars, only digits + optional dash/slash
        # + at most 3 alphanumeric chars — matches door numbers, not product codes.
        if re.match(r'^\d{1,5}[-/]?[A-Za-z0-9]{0,3}$', s) and len(s) <= 8:
            return False
        if _QTY_LINE.match(s):
            return False
        if _PA_MODE.match(s):
            return False
        if _SEPARATOR.match(s):
            return False
        if re.match(r'^\d+$', s):
            return False
        if _FINANCIAL_LINE.match(s):
            return False
        if _MERCURY_JUNK.search(s):
            return False
        if _PAYMENT_METHOD.match(s):
            return False
        if _METADATA_JUNK.search(s):
            return False
        if re.match(r'^(VAT|TAX|DISC|DISCOUNT)\s*[-–]?\s*\d+\s*%', s, re.IGNORECASE):
            return False
        if re.match(r'^LESS\b', s, re.IGNORECASE) and '%' in s:
            return False

        normalized = _normalize(s)
        if _SKIP_ITEM.search(normalized):
            has_unit = bool(_PRODUCT_UNITS.search(s))
            has_code = bool(_PRODUCT_CODE.search(s))
            if not (has_unit or has_code):
                return False
            if total_lines > 8 and line_idx > 0:
                if (line_idx / total_lines) > 0.75:
                    return False
        return True

    def _price_of(self, line: str) -> Optional[float]:
        s = line.strip()
        if _QTY_AT_PRICE.match(s):
            return None
        if re.match(r'^[₱P]?\s*[\d\.,OIl]+\s*[TXZVvy]?\s*$', s, re.IGNORECASE):
            s_norm = s.upper().replace('O', '0').replace('I', '1').replace('L', '1')
        else:
            s_norm = s
        m = _PRICE_ONLY.match(s_norm)
        if not m:
            return None
        try:
            return float(m.group(1).replace(',', ''))
        except ValueError:
            return None

    def _parse_qty_line(self, line: str) -> Tuple[Optional[int], Optional[float]]:
        m = _QTY_LINE.match(line.strip())
        if m:
            try:
                return int(m.group(1)), float(m.group(2).replace(',', ''))
            except ValueError:
                pass
        return None, None

    def _next_free(self, start: int, n: int, used: Set[int]) -> Optional[int]:
        for idx in range(start, n):
            if idx not in used:
                return idx
        return None

    def _next_price(self, start: int, n: int, used: Set[int],
                    lines: List[str], max_skip: int = 3) -> Optional[int]:
        skipped = 0
        for idx in range(start, n):
            if idx in used:
                continue
            s = lines[idx].strip()
            if self._price_of(s) is not None:
                return idx
            is_junk = (
                bool(_MERCURY_JUNK.search(s))
                or bool(_SEPARATOR.match(s))
                or bool(_PA_MODE.match(s))
                or bool(_PAYMENT_METHOD.match(s))
                or len(s) <= 2
                or bool(re.match(r'^\d{3,5}$', s))
            )
            if is_junk:
                skipped += 1
                if skipped >= max_skip:
                    return None
                continue
            return None
        return None

    def _has_price_before(self, lines: List[str], name_idx: int,
                           used: Set[int], zone_start: int = 0) -> bool:
        for back in range(name_idx - 1, zone_start - 1, -1):
            if back in used:
                continue
            s = lines[back].strip()
            if self._is_barcode(s):
                continue
            if self._price_of(s) is not None:
                return True
            break
        return False

    def _maybe_barcode(self, start: int, n: int, used: Set[int],
                        lines: List[str]) -> Tuple[Optional[str], Optional[int]]:
        k = self._next_free(start, n, used)
        if k is not None and self._is_barcode(lines[k]):
            return lines[k].strip(), k
        return None, None

    def _bp_disc_price_in_zone(self, lines: List[str], start: int, end: int) -> Optional[float]:
        for line in lines[start:end]:
            m = _BP_DISC_PRICE.search(line)
            if m:
                try:
                    val = float(m.group(1).replace(',', ''))
                    if val > 0:
                        return val
                except ValueError:
                    pass
        return None

    def _stated_item_count(self, lines: List[str]) -> Optional[int]:
        for line in lines:
            m = _ITEM_COUNT_LINE.search(line)
            if m:
                try:
                    return int(m.group(1))
                except (ValueError, IndexError):
                    pass
        _BARE = re.compile(r'^(\d+)\s*item', re.IGNORECASE)
        n = len(lines)
        for i, line in enumerate(lines):
            m = _BARE.match(line.strip())
            if m:
                prev_ok = i > 0 and lines[i-1].strip() in ('**', '*', '***')
                next_ok = i + 1 < n and lines[i+1].strip() in ('**', '*', '***')
                bare_ok = re.match(r'^\d+item', line.strip(), re.IGNORECASE)
                if prev_ok or next_ok or bare_ok:
                    try:
                        return int(m.group(1))
                    except (ValueError, IndexError):
                        pass
        _IP = re.compile(r'ITEMS?\s+PURCHAS(?:ED|EO|E)\s*[:#]?\s*(\d+)', re.IGNORECASE)
        for line in lines:
            m = _IP.search(line)
            if m:
                try:
                    return int(m.group(1))
                except (ValueError, IndexError):
                    pass
        return None

    def _cap_to_stated(self, items: List[Dict], stated: int) -> List[Dict]:
        def priority(item):
            name = item['name'].upper()
            score = 0
            if not item['sku']:   score += 10
            if len(name) <= 6:   score += 5
            if any(c in name for c in ['#', ':', '*']):   score += 8
            return score
        return sorted(items, key=priority, reverse=True)[:stated]

    def _infer_orphan(
        self,
        items: List[Dict],
        lines: List[str],
        used: Set[int],
        zone_start: int,
        zone_end: int,
        n: int,
    ) -> List[Dict]:
        orphan_name_idx = None
        orphan_barcode  = None
        orphan_name_line = None

        for ii in range(zone_start, zone_end):
            if ii in used:
                continue
            s_ii = lines[ii].strip()
            if not self._is_name(s_ii, n, ii):
                continue
            jj = ii + 1
            while jj < zone_end and jj in used:
                jj += 1
            if jj < zone_end and self._is_barcode(lines[jj].strip()):
                if orphan_name_idx is not None:
                    return items
                orphan_name_idx  = ii
                orphan_barcode   = lines[jj].strip()
                orphan_name_line = s_ii

        if orphan_name_idx is not None and orphan_barcode is not None:
            detected_sum = sum(it['price'] for it in items)
            receipt_total = None
            for ii2 in range(n):
                p_try = self._price_of(lines[ii2])
                if (p_try and p_try >= detected_sum
                        and not self._is_taxed_price(lines[ii2])):
                    if receipt_total is None or p_try < receipt_total:
                        receipt_total = p_try
            if receipt_total is not None:
                inferred = round(receipt_total - detected_sum, 2)
                if 0 < inferred < receipt_total:
                    items.append(self._build_item(
                        orphan_name_line, inferred, orphan_barcode,
                        source_idx=orphan_name_idx,
                    ))
                    logger.debug(
                        f"[PharmacyColumnExtractor] Orphan inference: "
                        f"{orphan_name_line} = {receipt_total} − {detected_sum} = {inferred}"
                    )
        return items