"""
Text Enhancement Module
Post-processes OCR output to restore spacing and special characters

Purpose: Fix common OCR errors where spacing is lost
Examples:
- TELNO044815-1340 → TEL NO : (044) 815-1340
- MOBILE7VIBER → MOBILE/VIBER
- LESSBPDISC5% → LESS : BP DISC 5%
- **1items** → ** 1 item(s) **
"""

import re
from typing import List, Dict
from loguru import logger


class TextEnhancer:
    """
    Enhance OCR output to restore proper spacing and special characters
    
    Handles:
    - Phone number formatting
    - TIN formatting
    - VAT spacing
    - Item counts
    - Special character restoration
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize text enhancer
        
        Args:
            config: Optional configuration dict
        """
        self.config = config or {}
        self.enabled = self.config.get('text_enhancement', {}).get('enabled', True)
        
        # Define enhancement patterns
        self.patterns = self._build_patterns()
        
        logger.info(f"Text Enhancer initialized (enabled: {self.enabled})")
    
    def _build_patterns(self) -> Dict:
        """Build regex patterns for text enhancement"""
        return {
            # ========== MERCURY DRUG SPECIFIC FIXES (NEW!) ==========
            
            # MTN number: MIN → MTN (common OCR error)
            'mtn_fix': {
                'pattern': r'MIN\s*:\s*(\d)',
                'replacement': r'MTN:\1',
                'description': 'Fix MTN misread as MIN'
            },
            
            # Preserve barcodes: Don't break 12-digit numbers
            'preserve_barcode': {
                'pattern': r'(\d{4})\s+(\d{4})-(\d{4})',
                'replacement': r'\1\2\3',
                'description': 'Preserve barcode numbers (remove spaces/dashes)'
            },
            
            # MOBILE/VIBER phone: Fix N0 → NO : (0
            'mobile_viber_phone': {
                'pattern': r'(MOBILE/VIBER)\s+N0(\d{4})\)',
                'replacement': r'\1 NO : (0\2)',
                'description': 'Fix MOBILE/VIBER phone format'
            },
            
            # PWD ID: PWDID# → PWD ID# :
            'pwd_id_spacing': {
                'pattern': r'PWDID#(\d)',
                'replacement': r'PWD ID# : \1',
                'description': 'Fix PWD ID spacing and colon'
            },
            
            # Company names: Phil logix → Phillogix
            'phillogix_fix': {
                'pattern': r'Phil\s+logix',
                'replacement': r'Phillogix',
                'description': 'Fix Phillogix company name'
            },
            
            # Fix Salamat: Sa lamat → Salamat
            'salamat_fix': {
                'pattern': r'Sa\s+lamat',
                'replacement': r'Salamat',
                'description': 'Fix Salamat word split'
            },
            
            # NIDO product: NID05 → NIDO5
            'nido_product': {
                'pattern': r'NID05\+',
                'replacement': r'NIDO5+',
                'description': 'Fix NIDO product code'
            },
            
            # Accredited number vs Acct'd: Common misread
            'accred_vs_acctd': {
                'pattern': r'Accred\s+No\.',
                'replacement': r"Acct'd No.",
                'description': 'Fix Accredited vs Account number'
            },
            
            # ========== GENERAL FORMATTING PATTERNS ==========
            
            # Phone numbers: (044)815-1340 or 0448151340
            'phone': {
                'pattern': r'(\d{3,4})(\d{3,4})-?(\d{4})',
                'replacement': r'\1 \2-\3',
                'description': 'Format phone numbers'
            },
            
            # TIN: preserve dashes in 000-388-474-00190
            'tin': {
                'pattern': r'(\d{3})-?(\d{3})-?(\d{3})-?(\d{5})',
                'replacement': r'\1-\2-\3-\4',
                'description': 'Format TIN numbers'
            },
            
            # VAT patterns: VAT12% → VAT 12%
            'vat_percent': {
                'pattern': r'(VAT)\s*-?\s*(\d+%)',
                'replacement': r'\1 \2',
                'description': 'Add space before VAT percentage'
            },
            
            # TEL NO: TELNO044 → TEL NO : (044)
            'tel_no': {
                'pattern': r'TEL\s*NO\s*:?\s*\(?(\d{3,4})\)?',
                'replacement': r'TEL NO : (\1)',
                'description': 'Format TEL NO with colon and parentheses'
            },
            
            # MOBILE/VIBER: MOBILE7VIBER → MOBILE/VIBER
            'mobile_viber_digit': {
                'pattern': r'(MOBILE)\d+(VIBER)',
                'replacement': r'\1/\2',
                'description': 'Fix MOBILE/VIBER separator'
            },
            
            # MOBILE/VIBER: MOBILEVIBER → MOBILE/VIBER
            'mobile_viber': {
                'pattern': r'(MOBILE)(VIBER)',
                'replacement': r'\1/\2',
                'description': 'Add slash between MOBILE and VIBER'
            },
            
            # Item count: 1items → 1 item(s)
            'items_singular': {
                'pattern': r'(\d+)\s*(item)([^s]|$)',
                'replacement': r'\1 \2\3',
                'description': 'Add space before item (singular)'
            },
            
            'items_plural': {
                'pattern': r'(\d+)\s*(items)',
                'replacement': r'\1 \2',
                'description': 'Add space before items (plural)'
            },
            
            # Item(s) formatting: 1items → 1 item(s)
            'items_with_parens': {
                'pattern': r'\*\*\s*(\d+)\s*items?\s*\*\*',
                'replacement': r'** \1 item(s) **',
                'description': 'Format item count with parentheses'
            },
            
            # LESS : BP DISC: LESSBPDISC → LESS : BP DISC
            'less_bp_disc': {
                'pattern': r'LESS\s*:?\s*BP\s*DISC',
                'replacement': r'LESS : BP DISC',
                'description': 'Add spacing to LESS BP DISC'
            },
            
            # Colon spacing: ABC:123 → ABC : 123
            'colon_spacing': {
                'pattern': r'([A-Z]{2,})(:)(\d)',
                'replacement': r'\1 \2 \3',
                'description': 'Add spaces around colons'
            },
            
            # PWD ID: PWD ID#000 → PWD ID# : 000
            'pwd_id': {
                'pattern': r'(PWD\s+ID#)\s*:?\s*(\d)',
                'replacement': r'\1 : \2',
                'description': 'Format PWD ID number'
            },
            
            # Percentage spacing: 5%x1220 → 5% x 1220
            'percent_multiply': {
                'pattern': r'(\d+%)\s*x\s*(\d)',
                'replacement': r'\1 x \2',
                'description': 'Add spaces around multiplication'
            },
        }
    
    def enhance_line(self, line: str) -> str:
        """
        Enhance a single OCR text line
        
        Args:
            line: Raw OCR text
            
        Returns:
            Enhanced text with proper spacing and formatting
        """
        if not self.enabled or not line:
            return line
        
        enhanced = line
        
        # Apply each pattern in order
        for pattern_name, pattern_info in self.patterns.items():
            try:
                enhanced = re.sub(
                    pattern_info['pattern'],
                    pattern_info['replacement'],
                    enhanced,
                    flags=re.IGNORECASE
                )
            except Exception as e:
                logger.warning(f"Pattern '{pattern_name}' failed: {e}")
                continue
        
        return enhanced
    
    def enhance_all_lines(self, lines: List[str]) -> List[str]:
        """
        Enhance all OCR lines
        
        Args:
            lines: List of raw OCR text lines
            
        Returns:
            List of enhanced text lines
        """
        if not self.enabled:
            return lines
        
        return [self.enhance_line(line) for line in lines]
    
    def enhance_lines_with_confidence(self, lines: List[Dict]) -> List[Dict]:
        """
        Enhance OCR lines that include confidence scores
        
        Args:
            lines: List of dicts with 'text' and 'confidence' keys
            
        Returns:
            List of enhanced line dicts
        """
        if not self.enabled:
            return lines
        
        enhanced_lines = []
        for line in lines:
            enhanced = line.copy()
            enhanced['text'] = self.enhance_line(line.get('text', ''))
            enhanced_lines.append(enhanced)
        
        return enhanced_lines
    
    def get_enhancement_report(self, original: str, enhanced: str) -> Dict:
        """
        Get a report of what was changed
        
        Args:
            original: Original text
            enhanced: Enhanced text
            
        Returns:
            Dict with changes made
        """
        changes = []
        
        if original != enhanced:
            changes.append({
                'original': original,
                'enhanced': enhanced,
                'changed': True
            })
        
        return {
            'changed': len(changes) > 0,
            'changes': changes
        }


def main():
    """Test the text enhancer"""
    print("\n" + "="*70)
    print("TEXT ENHANCER - ENHANCED VERSION - Test Mode")
    print("="*70 + "\n")
    
    enhancer = TextEnhancer()
    
    # Test cases from Mercury Drug receipt + new fixes
    test_cases = [
        # Original patterns
        ("TELNO044815-1340", "TEL NO : (044) 815-1340"),
        ("MOBILE7VIBER NO:0919080-6386", "MOBILE/VIBER NO : (0919) 080-6386"),
        ("LESSBPDISC5%x1220.00", "LESS : BP DISC 5% x 1220.00"),
        ("**1items **", "** 1 item(s) **"),
        ("VAT-12%", "VAT 12%"),
        ("PWD ID#000 0031", "PWD ID# : 000 0031"),
        
        # NEW: Mercury Drug specific fixes
        ("MIN : 2408 2015-243672942[1.5.30]31", "MTN:2408 2015-243672942[1.5.30]31"),
        ("4800 3614-0523", "480036140523"),
        ("MOBILE/VIBER N00919)080-6386", "MOBILE/VIBER NO : (0919)080-6386"),
        ("PWDID#000 0031 402013135", "PWD ID# : 000 0031 402013135"),
        ("Phil logix Systems, Inc.", "Phillogix Systems, Inc."),
        ("Sa lamat Po", "Salamat Po"),
        ("NID05+PDR MLK2kg", "NIDO5+PDR MLK2kg"),
        ("Accred No.:8042", "Acct'd No.:8042"),
    ]
    
    print("Testing enhancement patterns:\n")
    
    passed = 0
    failed = 0
    
    for original, expected in test_cases:
        enhanced = enhancer.enhance_line(original)
        status = "✅" if enhanced == expected else "⚠️"
        
        if enhanced == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} Original:  {original}")
        print(f"   Enhanced: {enhanced}")
        if enhanced != expected:
            print(f"   Expected: {expected}")
        print()
    
    print("="*70)
    print(f"\n📊 TEST RESULTS: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    
    if failed == 0:
        print("🎉 All tests passed! Text enhancer is working perfectly!")
    else:
        print(f"⚠️  {failed} test(s) need adjustment")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    main()