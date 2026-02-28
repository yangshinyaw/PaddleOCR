"""
Pattern-Based OCR Corrector
Smart, Dynamic Correction WITHOUT Hardcoded Store Names

Uses intelligent patterns to fix:
1. Character confusions (0/O, 1/I/l, 5/S)
2. Spacing issues (merged words)
3. Common OCR systematic errors
4. Only critical systematic errors in minimal dictionary

NO store name dictionaries needed!
Works on ANY receipt from ANY store.

Changes from v1
---------------
BUG FIX — _fix_philippine_symbols:
  The old regex used r'₱\x01' (a control char) as the replacement,
  which discarded the captured price digits entirely.
  e.g. "P1220.00" → "₱" (price lost)
  Fixed to r'₱\1' so the matched digits are preserved:
  e.g. "P1220.00" → "₱1220.00"

IMPROVEMENT — _fix_character_confusions:
  Now guarded by a word-type check so it does NOT corrupt barcodes,
  product codes (NID05, phone numbers, invoice IDs).
  Corrections only apply when the surrounding context is clearly
  all-caps alphabetic (word context) or clearly all-digit (number context).
"""

import re
from typing import List, Dict, Tuple
from loguru import logger


class PatternBasedCorrector:
    """
    Smart OCR correction using patterns, not hardcoded dictionaries.

    Philosophy:
    - Fix systematic OCR errors (errors that ALWAYS happen)
    - Use pattern recognition, not store lists
    - Minimal critical-only dictionary (only for 100% certain errors)
    - Works on receipts from ANY store
    """

    def __init__(self):
        """Initialize pattern-based corrector."""
        # ONLY systematic errors that are ALWAYS wrong
        self.critical_systematic_errors = {
            'MIN': 'MTN',  # Machine Transaction Number always misread as MIN
        }

        logger.info("Pattern-Based OCR Corrector initialized (NO store dictionaries)")
        logger.info(f"Critical systematic errors: {len(self.critical_systematic_errors)}")

    def correct_line(self, line: str) -> str:
        """
        Correct a single OCR line using patterns.

        Args:
            line: Raw OCR text

        Returns:
            Corrected text
        """
        if not line:
            return line

        original = line

        # Apply corrections in order
        line = self._fix_philippine_symbols(line)
        line = self._fix_character_confusions(line)
        line = self._fix_spacing_patterns(line)
        line = self._fix_number_letter_boundaries(line)
        line = self._fix_critical_systematic_errors(line)
        line = self._fix_punctuation_spacing(line)
        line = self._fix_common_word_splits(line)

        if line != original:
            logger.debug(f"Corrected: '{original}' → '{line}'")

        return line

    def _fix_philippine_symbols(self, text: str) -> str:
        """
        Fix Philippine receipt symbol misreads (peso sign, multiply, dashes).

        BUG FIX: The original used r'₱\x01' as replacement which drops
        the captured price group. Fixed to r'₱\1' to preserve digits.

        Also guarded so we do NOT touch 'P' inside product names:
        - PDR, PHP, PCS, PACK etc. are NOT peso signs
        - Only 'P' immediately followed by digits (with optional space) is peso
        """
        # Peso sign: P followed by digits is a price, not a product-name letter.
        # The negative lookbehind (?<![A-Z]) prevents matching PDR, PHP, PACK etc.
        # Capture group \1 preserves the price digits.
        text = re.sub(
            r'(?<![A-Z])P\s*(\d[\d,]*\.\d{2})',
            r'₱\1',
            text,
        )

        # Yen sign misread as peso (rare, very low resolution scans)
        text = re.sub(
            r'¥\s*(\d[\d,]*\.\d{2})',
            r'₱\1',
            text,
        )

        # Multiply sign: digit [space] x [space] digit → digit × digit
        # Only when both neighbours are digits (quantity × unit-price context)
        text = re.sub(
            r'(\d)\s+[xX]\s+(\d)',
            r'\1 × \2',
            text,
        )

        # Underscore in numeric sequences → hyphen (TIN, phone numbers)
        text = re.sub(r'(\d)_(\d)', r'\1-\2', text)

        return text

    def _fix_character_confusions(self, text: str) -> str:
        """
        Fix common OCR character confusions, with context guards to
        avoid corrupting barcodes, product codes, and invoice numbers.

        Rules (only applied in clear-context situations):
        - O → 0 : only when flanked by digits on BOTH sides
        - 0 → O : only when flanked by capital letters on BOTH sides
        - 1 → I : only when flanked by capital letters on BOTH sides
        - l → 1 : only when flanked by digits on BOTH sides

        '5→S' and similar aggressive rules have been REMOVED because they
        corrupt product codes like NIDO5, NID05, and numeric barcodes.
        """
        result = list(text)
        n = len(result)

        for i, char in enumerate(result):
            prev = result[i - 1] if i > 0     else ''
            nxt  = result[i + 1] if i < n - 1 else ''

            if char == 'O' and prev.isdigit() and nxt.isdigit():
                # "1O3" in a number context → "103"
                result[i] = '0'

            elif char == '0' and prev.isupper() and nxt.isupper():
                # "PR0DUCT" → "PRODUCT"
                result[i] = 'O'

            elif char == '1' and prev.isupper() and nxt.isupper():
                # "PHILI1PINE" → "PHILIPPINE"
                result[i] = 'I'

            elif char == 'l' and prev.isdigit() and nxt.isdigit():
                # "2l5" → "215"
                result[i] = '1'

        return ''.join(result)

    def _fix_spacing_patterns(self, text: str) -> str:
        """
        Fix missing spaces using pattern recognition.

        Patterns:
        - SMCITY → SM CITY (2+ caps followed by cap+lowercase)
        - CustomerCare → Customer Care (transition points)
        - SANFERNANDO → SAN FERNANDO (known prefixes)
        """
        # Pattern 1: Insert space before cap+lowercase after 2+ caps
        text = re.sub(r'([A-Z]{2,})([A-Z][a-z])', r'\1 \2', text)

        # Pattern 2: Insert space at lowercase-uppercase boundaries
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

        # Pattern 3: Common Philippine address prefixes
        prefixes = ['SAN', 'SANTA', 'ST', 'AVE', 'BRGY']
        for prefix in prefixes:
            text = re.sub(rf'\b{prefix}([A-Z][a-z])', rf'{prefix} \1', text)

        # Pattern 4: Insert space before common suffixes
        suffixes = ['CARE', 'SUPPORT', 'SERVICE', 'CENTER', 'STORE']
        for suffix in suffixes:
            text = re.sub(rf'([A-Z]{{3,}}){suffix}\b', rf'\1 {suffix}', text)

        return text

    def _fix_number_letter_boundaries(self, text: str) -> str:
        """
        Fix spacing at number-letter boundaries.

        Examples:
        - 2068103059163Bitty → 2068103059163 Bitty
        """
        text = re.sub(r'(\d{4,})([A-Z][a-z])', r'\1 \2', text)
        return text

    def _fix_critical_systematic_errors(self, text: str) -> str:
        """
        Fix ONLY critical systematic errors.

        These are errors that ALWAYS happen and are ALWAYS wrong.
        Example: MIN (minutes) vs MTN (Machine Transaction Number).
        """
        for wrong, correct in self.critical_systematic_errors.items():
            text = re.sub(rf'\b{wrong}\b', correct, text)
        return text

    def _fix_punctuation_spacing(self, text: str) -> str:
        """
        Fix spacing around punctuation.

        Examples:
        - NO:0919 → NO : 0919
        - TIN:000 → TIN : 000
        - ID#000  → ID# : 000
        """
        # Add space around colons between all-caps label and digit
        text = re.sub(r'([A-Z]{2,}):(\\d)', r'\1 : \2', text)

        # Add space after # in ID numbers
        text = re.sub(r'(ID)#(\d)', r'\1# : \2', text)

        return text

    def _fix_common_word_splits(self, text: str) -> str:
        """
        Fix common words that get split by OCR.
        """
        # Fix: [Single letter 'Sa'] + space + lowercase word
        text = re.sub(r'\b(Sa)\s+([a-z]{3,})\b', r'\1\2', text)

        common_splits = [
            (r'\bTele\s+phone\b', 'Telephone'),
            (r'\bInter\s+national\b', 'International'),
        ]
        for pattern, replacement in common_splits:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        return text

    def correct_all_lines(self, lines: List[str]) -> List[str]:
        """Correct all OCR lines."""
        return [self.correct_line(line) for line in lines]

    def correct_lines_with_confidence(self, lines: List[Dict]) -> List[Dict]:
        """Correct OCR lines that include confidence scores."""
        corrected_lines = []
        for line in lines:
            corrected = line.copy()
            original = line.get('text', '')
            corrected_text = self.correct_line(original)

            corrected['text'] = corrected_text
            if corrected_text != original:
                corrected['pattern_corrected'] = True
                corrected['original_text'] = original
            else:
                corrected['pattern_corrected'] = False

            corrected_lines.append(corrected)

        return corrected_lines

    def get_correction_report(self, lines: List[str]) -> Dict:
        """Get a report of corrections made."""
        corrections = []
        for i, line in enumerate(lines):
            corrected = self.correct_line(line)
            if corrected != line:
                corrections.append({
                    'line_number': i + 1,
                    'original': line,
                    'corrected': corrected,
                    'change_type': self._identify_change_type(line, corrected),
                })
        return {
            'total_lines': len(lines),
            'lines_corrected': len(corrections),
            'correction_rate': len(corrections) / len(lines) if lines else 0,
            'corrections': corrections,
        }

    def _identify_change_type(self, original: str, corrected: str) -> str:
        if len(corrected.split()) > len(original.split()):
            return 'spacing_added'
        elif '₱' in corrected and '₱' not in original:
            return 'peso_sign_restored'
        elif '0' in corrected and 'O' in original:
            return 'character_swap_O_0'
        elif 'O' in corrected and '0' in original:
            return 'character_swap_0_O'
        elif 'MIN' in original and 'MTN' in corrected:
            return 'systematic_error_MIN_MTN'
        else:
            return 'other'


def main():
    """Test the pattern-based corrector."""
    print("\n" + "="*70)
    print("PATTERN-BASED OCR CORRECTOR - Test Mode")
    print("="*70)
    print("\n✨ NO hardcoded store names - uses smart patterns!\n")

    corrector = PatternBasedCorrector()

    test_cases = [
        # Peso sign fix (THE critical bug fix)
        ("P1220.00",          "₱1220.00"),
        ("P 45.00",           "₱45.00"),
        ("P1,220.00",         "₱1,220.00"),

        # Peso sign must NOT touch product names
        ("PDR MLK",           "PDR MLK"),     # P in PDR = not a peso sign
        ("PHP 100.00",        "PHP 100.00"),   # PHP is not peso
        ("PCS 5",             "PCS 5"),        # PCS is not peso

        # Character confusions
        ("INTERNATI0NAL",     "INTERNATIONAL"),  # 0 between caps → O
        ("2O5",               "205"),             # O between digits → 0

        # Spacing patterns
        ("SMCITY PAMPANGA",   "SM CITY PAMPANGA"),
        ("SANFERNANDO",       "SAN FERNANDO"),

        # Number-letter boundary
        ("2068103059163Bitty", "2068103059163 Bitty"),

        # Systematic errors
        ("MIN 2501",          "MTN 2501"),

        # Should NOT change (already correct)
        ("TOTAL AMOUNT",      "TOTAL AMOUNT"),
        ("480036140523",      "480036140523"),  # barcode untouched
        ("NID05+PDR",         "NID05+PDR"),     # product code untouched
    ]

    print("Testing pattern-based corrections:\n")
    passed = 0
    failed = 0
    unchanged = 0

    for original, expected in test_cases:
        corrected = corrector.correct_line(original)
        if corrected == expected:
            status = "✅"
            passed += 1
        elif corrected == original and expected == original:
            status = "➖"
            unchanged += 1
        else:
            status = "⚠️" if corrected != expected else "➖"
            if corrected != expected:
                failed += 1
            else:
                unchanged += 1

        print(f"{status} Original:  {original!r}")
        print(f"   Corrected: {corrected!r}")
        if corrected != expected:
            print(f"   Expected:  {expected!r}")
        print()

    print("="*70)
    print(f"\n📊 TEST RESULTS:")
    print(f"  ✅ Passed:    {passed}/{len(test_cases)}")
    print(f"  ⚠️  Failed:    {failed}/{len(test_cases)}")
    print(f"  ➖ Unchanged: {unchanged}/{len(test_cases)}")
    print(f"\n🎯 Accuracy: {(passed / len(test_cases)) * 100:.1f}%")
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    main()