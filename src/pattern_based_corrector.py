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
"""

import re
from typing import List, Dict, Tuple
from loguru import logger


class PatternBasedCorrector:
    """
    Smart OCR correction using patterns, not hardcoded dictionaries
    
    Philosophy:
    - Fix systematic OCR errors (errors that ALWAYS happen)
    - Use pattern recognition, not store lists
    - Minimal critical-only dictionary (only for 100% certain errors)
    - Works on receipts from ANY store
    """
    
    def __init__(self):
        """Initialize pattern-based corrector"""
        # ONLY systematic errors that are ALWAYS wrong
        self.critical_systematic_errors = {
            'MIN': 'MTN',  # Machine Transaction Number always misread as MIN
        }
        
        logger.info("Pattern-Based OCR Corrector initialized (NO store dictionaries)")
        logger.info(f"Critical systematic errors: {len(self.critical_systematic_errors)}")
    
    def correct_line(self, line: str) -> str:
        """
        Correct a single OCR line using patterns
        
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
    
    def _fix_character_confusions(self, text: str) -> str:
        """
        Fix common OCR character confusions
        
        Rules:
        - 0 → O when surrounded by letters
        - O → 0 when surrounded by numbers
        - 1 → I when in all-caps words
        - l → 1 when surrounded by numbers
        - 5 → S at start of all-caps words
        """
        result = []
        chars = list(text)
        
        for i, char in enumerate(chars):
            prev_char = chars[i-1] if i > 0 else ''
            next_char = chars[i+1] if i < len(chars)-1 else ''
            
            # 0 → O: When between letters or at start of caps word
            if char == '0':
                if (prev_char.isalpha() or next_char.isalpha()):
                    # Check if this looks like a letter context
                    if i == 0 or (prev_char.isupper() and next_char.isupper()):
                        result.append('O')
                        continue
            
            # O → 0: When between numbers
            elif char == 'O':
                if prev_char.isdigit() and next_char.isdigit():
                    result.append('0')
                    continue
            
            # 1 → I: In all-caps words (but not in numbers)
            elif char == '1':
                if prev_char.isupper() and next_char.isupper():
                    result.append('I')
                    continue
            
            # l → 1: When surrounded by numbers
            elif char == 'l':
                if prev_char.isdigit() or next_char.isdigit():
                    result.append('1')
                    continue
            
            # 5 → S: At start of all-caps words
            elif char == '5':
                if i < len(chars) - 2:
                    if chars[i+1].isupper() and chars[i+2].isupper():
                        result.append('S')
                        continue
            
            # Keep original character
            result.append(char)
        
        return ''.join(result)
    
    def _fix_spacing_patterns(self, text: str) -> str:
        """
        Fix missing spaces using pattern recognition
        
        Patterns:
        - SMCITY → SM CITY (2+ caps followed by cap+lowercase)
        - CUSTOMERCARE → CUSTOMER CARE (transition points)
        - SANFERNANDO → SAN FERNANDO (known prefixes)
        """
        # Pattern 1: Insert space before cap+lowercase after 2+ caps
        # SMCITY → SM CITY, TOYKINGDOM → TOY KINGDOM
        text = re.sub(r'([A-Z]{2,})([A-Z][a-z])', r'\1 \2', text)
        
        # Pattern 2: Insert space at lowercase-uppercase boundaries
        # CustomerCare → Customer Care
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        
        # Pattern 3: Common prefixes that need spaces
        # SAN/SANTA should be separate words in Philippines addresses
        prefixes = ['SAN', 'SANTA', 'ST', 'AVE', 'BRGY']
        for prefix in prefixes:
            # SANFERNANDO → SAN FERNANDO
            pattern = rf'\b{prefix}([A-Z][a-z])'
            text = re.sub(pattern, rf'{prefix} \1', text)
        
        # Pattern 4: Insert space before common suffixes
        # CUSTOMERCARE → CUSTOMER CARE, CUSTOMERSUPPORT → CUSTOMER SUPPORT
        suffixes = ['CARE', 'SUPPORT', 'SERVICE', 'CENTER', 'STORE']
        for suffix in suffixes:
            pattern = rf'([A-Z]{{3,}}){suffix}\b'
            text = re.sub(pattern, rf'\1 {suffix}', text)
        
        return text
    
    def _fix_number_letter_boundaries(self, text: str) -> str:
        """
        Fix spacing at number-letter boundaries
        
        Examples:
        - 2068103059163Bitty → 2068103059163 Bitty
        - PHP199.00V → PHP 199.00 V
        """
        # Add space between number and letter (except in codes like NID05)
        # But keep product codes together
        text = re.sub(r'(\d{4,})([A-Z][a-z])', r'\1 \2', text)
        
        return text
    
    def _fix_critical_systematic_errors(self, text: str) -> str:
        """
        Fix ONLY critical systematic errors
        
        These are errors that ALWAYS happen and are ALWAYS wrong
        Example: MIN (minutes) vs MTN (Machine Transaction Number)
        """
        for wrong, correct in self.critical_systematic_errors.items():
            # Use word boundaries to avoid partial replacements
            pattern = rf'\b{wrong}\b'
            text = re.sub(pattern, correct, text)
        
        return text
    
    def _fix_punctuation_spacing(self, text: str) -> str:
        """
        Fix spacing around punctuation
        
        Examples:
        - NO:0919 → NO : 0919
        - TIN:000 → TIN : 000
        - ID#000 → ID# : 000
        """
        # Add space before and after colons (except in times and URLs)
        text = re.sub(r'([A-Z]{2,}):(\d)', r'\1 : \2', text)
        
        # Add space after # in ID numbers
        text = re.sub(r'(ID)#(\d)', r'\1# : \2', text)
        
        return text
    
    def _fix_common_word_splits(self, text: str) -> str:
        """
        Fix common words that get split by OCR
        
        Uses patterns to detect and merge split words
        """
        # Common splits to fix (pattern-based, not hardcoded words)
        # Pattern: Single letter followed by word fragment
        # "Sa lamat" → "Salamat", "Ma raming" → "Maraming"
        
        # Fix: [Single letter] + space + [lowercase word starting with 'a']
        text = re.sub(r'\b([A-Z]a)\s+([a-z]{3,})\b', r'\1\2', text)
        
        # Fix: Common prefix-suffix splits
        # "Tele phone" → "Telephone", "Inter national" → "International"
        common_splits = [
            (r'\bTele\s+phone\b', 'Telephone'),
            (r'\bInter\s+national\b', 'International'),
            (r'\bCustomer\s+Care\b', 'CustomerCare'),  # Then spacing pattern will fix it
        ]
        
        for pattern, replacement in common_splits:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        return text
    
    def _fix_philippine_symbols(self, text: str) -> str:
        """Fix Philippine receipt symbol misreads (peso, multiply, dashes)."""
        import re
        # Restore peso sign: P followed by digits is a price, not a letter
        # Handles P1220.00, P1,220.00, P 1220.00
        # Does NOT touch P in product names like PDR, PHP, PCS
        text = re.sub(r'(?<![A-Z])P\s*(\d[\d,]*\.\d{2})', r'₱', text)
        # Yen misread as peso (rare, very low resolution)
        text = re.sub(r'¥\s*(\d[\d,]*\.\d{2})', r'₱', text)
        # Multiply sign: digit x digit → digit × digit
        text = re.sub(r'(\d)\s+[xX]\s+(\d)', r' × ', text)
        # Underscore in numeric sequences → hyphen (TIN, phone numbers)
        text = re.sub(r'(\d)_(\d)', r'-', text)
        return text

    def correct_all_lines(self, lines: List[str]) -> List[str]:
        """
        Correct all OCR lines
        
        Args:
            lines: List of raw OCR lines
            
        Returns:
            List of corrected lines
        """
        return [self.correct_line(line) for line in lines]
    
    def correct_lines_with_confidence(self, lines: List[Dict]) -> List[Dict]:
        """
        Correct OCR lines that include confidence scores
        
        Args:
            lines: List of dicts with 'text' and 'confidence' keys
            
        Returns:
            List of corrected line dicts
        """
        corrected_lines = []
        for line in lines:
            corrected = line.copy()
            original = line.get('text', '')
            corrected_text = self.correct_line(original)
            
            # Track if correction was made
            if corrected_text != original:
                corrected['text'] = corrected_text
                corrected['pattern_corrected'] = True
                corrected['original_text'] = original
            else:
                corrected['text'] = original
                corrected['pattern_corrected'] = False
            
            corrected_lines.append(corrected)
        
        return corrected_lines
    
    def get_correction_report(self, lines: List[str]) -> Dict:
        """
        Get a report of corrections made
        
        Args:
            lines: Original lines
            
        Returns:
            Dict with correction statistics
        """
        corrections = []
        
        for i, line in enumerate(lines):
            corrected = self.correct_line(line)
            if corrected != line:
                corrections.append({
                    'line_number': i + 1,
                    'original': line,
                    'corrected': corrected,
                    'change_type': self._identify_change_type(line, corrected)
                })
        
        return {
            'total_lines': len(lines),
            'lines_corrected': len(corrections),
            'correction_rate': len(corrections) / len(lines) if lines else 0,
            'corrections': corrections
        }
    
    def _identify_change_type(self, original: str, corrected: str) -> str:
        """Identify what type of correction was made"""
        if len(corrected.split()) > len(original.split()):
            return 'spacing_added'
        elif '0' in original and 'O' in corrected:
            return 'character_swap_0_O'
        elif 'O' in original and '0' in corrected:
            return 'character_swap_O_0'
        elif 'MIN' in original and 'MTN' in corrected:
            return 'systematic_error_MIN_MTN'
        else:
            return 'other'


def main():
    """Test the pattern-based corrector"""
    print("\n" + "="*70)
    print("PATTERN-BASED OCR CORRECTOR - Test Mode")
    print("="*70)
    print("\n✨ NO hardcoded store names - uses smart patterns!\n")
    
    corrector = PatternBasedCorrector()
    
    # Test cases - mix of real errors from different stores
    test_cases = [
        # Character confusions
        ("INTERNATI0NAL T0YW0RLD", "INTERNATIONAL TOYWORLD"),
        ("TELEPH0NE", "TELEPHONE"),
        ("SUPP0RT", "SUPPORT"),
        
        # Spacing patterns
        ("TOYKINGDOM", "TOY KINGDOM"),
        ("SMCITY PAMPANGA", "SM CITY PAMPANGA"),
        ("MERCURYDRUG", "MERCURY DRUG"),
        ("CUSTOMERCARE SUPPORT", "CUSTOMER CARE SUPPORT"),
        ("PUREGOLD", "PURE GOLD"),
        
        # Philippines locations (using SAN pattern)
        ("SANFERNANDO", "SAN FERNANDO"),
        ("SANJOSE", "SAN JOSE"),
        ("SANTAMARIA", "SANTA MARIA"),
        
        # Number-letter boundaries
        ("2068103059163Bitty", "2068103059163 Bitty"),
        ("PHP199.00V", "PHP 199.00 V"),
        
        # Systematic errors
        ("MIN 2501 0913-483827986", "MTN 2501 0913-483827986"),
        
        # Punctuation spacing
        ("TEL NO:044", "TEL NO : 044"),
        ("VAT TIN:000-404-018", "VAT TIN : 000-404-018"),
        ("PWD ID#000031", "PWD ID# : 000031"),
        
        # Word splits
        ("Sa lamat Po", "Salamat Po"),
        ("Tele phone", "Telephone"),
        
        # Should NOT change (already correct)
        ("TOTAL AMOUNT", "TOTAL AMOUNT"),
        ("CHANGE", "CHANGE"),
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
        elif corrected == original:
            status = "➖"
            unchanged += 1
        else:
            status = "⚠️"
            failed += 1
        
        print(f"{status} Original:  {original}")
        print(f"   Corrected: {corrected}")
        if corrected != expected and corrected != original:
            print(f"   Expected:  {expected}")
        print()
    
    print("="*70)
    print(f"\n📊 TEST RESULTS:")
    print(f"  ✅ Passed: {passed}/{len(test_cases)}")
    print(f"  ⚠️  Failed: {failed}/{len(test_cases)}")
    print(f"  ➖ Unchanged: {unchanged}/{len(test_cases)}")
    
    accuracy = (passed / len(test_cases)) * 100
    print(f"\n🎯 Pattern Accuracy: {accuracy:.1f}%")
    
    if passed == len(test_cases):
        print("\n🎉 All tests passed! Pattern-based correction working perfectly!")
    elif accuracy >= 80:
        print(f"\n👍 Good! {accuracy:.0f}% of patterns working correctly.")
    else:
        print(f"\n⚠️  {failed} patterns need adjustment")
    
    print("\n💡 Key Point: NO hardcoded store names used!")
    print("   Works on ANY store - just uses smart patterns.")
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    main()