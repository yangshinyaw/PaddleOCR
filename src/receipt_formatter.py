"""
Enhanced Receipt Text Formatter - FULLY OPTIMIZED
Formats OCR text to match receipt layout perfectly

NEW FEATURES:
- Adaptive row tolerance (adjusts to font size)
- Multi-column detection
- Section detection (header/items/footer)
- Multi-line item merging
- Smart spacing based on positions
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from loguru import logger


class ReceiptTextFormatter:
    """
    OPTIMIZED formatter that preserves receipt structure
    
    Features:
    - Adaptive tolerance (auto-adjusts to line height)
    - Multi-column support (item | price columns)
    - Section detection (header, items, footer)
    - Multi-line item handling
    """
    
    def __init__(self, row_tolerance: int = 15):
        """
        Args:
            row_tolerance: Base pixels tolerance for same row (auto-adjusted)
        """
        self.base_row_tolerance = row_tolerance
        self.min_line_height = 10
        self.max_line_height = 50
        self.column_threshold = 100  # Min pixels between columns
    
    def format_receipt_text(self, ocr_lines: List[Dict]) -> Dict:
        """
        Format OCR lines with ALL optimizations
        
        Args:
            ocr_lines: List of OCR results with text, confidence, bbox
        
        Returns:
            Complete formatted result with rows, sections, structure
        """
        if not ocr_lines:
            return {
                'formatted_text': '',
                'rows': [],
                'total_rows': 0,
                'original_lines': 0,
                'sections': [],
                'structure': {}
            }
        
        logger.info(f"Formatting {len(ocr_lines)} lines with optimizations")
        
        # STEP 1: Calculate adaptive tolerance
        tolerance = self._calculate_adaptive_tolerance(ocr_lines)
        logger.debug(f"Adaptive tolerance: {tolerance}px")
        
        # STEP 2: Sort by position
        sorted_lines = self._sort_lines_by_position(ocr_lines)
        
        # STEP 3: Group into rows
        rows = self._group_lines_into_rows(sorted_lines, tolerance)
        
        # STEP 4: Detect columns in each row
        formatted_rows = self._format_rows_with_columns(rows)
        
        # STEP 5: Detect sections
        sections = self._detect_sections(formatted_rows)
        
        # STEP 6: Merge multi-line items
        merged_rows = self._merge_multiline_items(formatted_rows)
        
        # STEP 7: Generate final text
        formatted_text = '\n'.join([row['text'] for row in merged_rows])
        
        # STEP 8: Analyze structure
        structure = self._analyze_structure(merged_rows, sections)
        
        result = {
            'formatted_text': formatted_text,
            'rows': merged_rows,
            'total_rows': len(merged_rows),
            'original_lines': len(ocr_lines),
            'sections': sections,
            'structure': structure
        }
        
        logger.success(f"Formatted: {len(ocr_lines)} lines → {len(merged_rows)} rows, "
                      f"{len(sections)} sections")
        
        return result
    
    # ==================== ADAPTIVE TOLERANCE ====================
    
    def _calculate_adaptive_tolerance(self, lines: List[Dict]) -> int:
        """
        Calculate row tolerance based on actual line heights
        Adjusts to receipt font size automatically
        """
        heights = []
        
        for line in lines:
            bbox = line.get('bbox', [])
            if len(bbox) == 4:
                y_coords = [point[1] for point in bbox]
                height = max(y_coords) - min(y_coords)
                
                if self.min_line_height <= height <= self.max_line_height:
                    heights.append(height)
        
        if heights:
            avg_height = np.median(heights)
            # Tolerance = 50% of average line height
            tolerance = max(self.base_row_tolerance, int(avg_height * 0.5))
            return tolerance
        
        return self.base_row_tolerance
    
    # ==================== SORTING & GROUPING ====================
    
    def _sort_lines_by_position(self, lines: List[Dict]) -> List[Dict]:
        """Sort lines top-to-bottom, then left-to-right"""
        def get_position(line):
            bbox = line.get('bbox', [])
            if len(bbox) == 4:
                y = (bbox[0][1] + bbox[1][1]) / 2
                x = (bbox[0][0] + bbox[3][0]) / 2
                return (y, x)
            return (0, 0)
        
        return sorted(lines, key=get_position)
    
    def _group_lines_into_rows(self, sorted_lines: List[Dict], tolerance: int) -> List[List[Dict]]:
        """Group lines into rows based on Y position"""
        if not sorted_lines:
            return []
        
        rows = []
        current_row = [sorted_lines[0]]
        current_y = self._get_y_position(sorted_lines[0])
        
        for line in sorted_lines[1:]:
            line_y = self._get_y_position(line)
            
            if abs(line_y - current_y) <= tolerance:
                current_row.append(line)
            else:
                # Sort row left-to-right before saving
                current_row.sort(key=lambda l: self._get_x_position(l))
                rows.append(current_row)
                current_row = [line]
                current_y = line_y
        
        if current_row:
            current_row.sort(key=lambda l: self._get_x_position(l))
            rows.append(current_row)
        
        return rows
    
    # ==================== COLUMN DETECTION ====================
    
    def _format_rows_with_columns(self, rows: List[List[Dict]]) -> List[Dict]:
        """Format rows with column detection"""
        formatted_rows = []
        
        for row_num, row in enumerate(rows, 1):
            # Detect columns in this row
            columns = self._detect_columns_in_row(row)
            
            # Format text with proper spacing
            row_text = self._format_row_text_with_spacing(row, columns)
            
            # Calculate confidence
            confidences = [item.get('confidence', 0) for item in row]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            formatted_rows.append({
                'row_number': row_num,
                'text': row_text,
                'items': row,
                'item_count': len(row),
                'columns': len(columns),
                'confidence': round(float(avg_confidence), 3),
                'y_position': self._get_y_position(row[0])
            })
        
        return formatted_rows
    
    def _detect_columns_in_row(self, row: List[Dict]) -> List[List[Dict]]:
        """Detect column breaks based on X spacing"""
        if len(row) <= 1:
            return [row]
        
        columns = [[row[0]]]
        
        for item in row[1:]:
            prev_item = columns[-1][-1]
            
            # Calculate gap
            prev_x_right = max([point[0] for point in prev_item['bbox']])
            curr_x_left = min([point[0] for point in item['bbox']])
            gap = curr_x_left - prev_x_right
            
            # Large gap = new column
            if gap >= self.column_threshold:
                columns.append([item])
            else:
                columns[-1].append(item)
        
        return columns
    
    def _format_row_text_with_spacing(self, row: List[Dict], columns: List[List[Dict]]) -> str:
        """Format row text with smart spacing"""
        if len(columns) == 1:
            # Single column - join with spaces
            return ' '.join([item['text'] for item in row])
        
        # Multiple columns - add extra spacing
        column_texts = []
        for column in columns:
            column_text = ' '.join([item['text'] for item in column])
            column_texts.append(column_text)
        
        return '  '.join(column_texts)  # Double space between columns
    
    # ==================== SECTION DETECTION ====================
    
    def _detect_sections(self, rows: List[Dict]) -> List[Dict]:
        """
        Detect receipt sections
        
        Returns:
            List of sections (header, items, footer)
        """
        if not rows:
            return []
        
        sections = []
        total_rows = len(rows)
        
        # Header: First 3-5 rows (merchant, address, date)
        header_end = min(5, total_rows)
        sections.append({
            'type': 'header',
            'start_row': 1,
            'end_row': header_end,
            'rows': rows[:header_end],
            'description': 'Merchant info, date, address'
        })
        
        # Footer: Last 3-5 rows (totals, payment)
        footer_start = max(header_end, total_rows - 5)
        footer_rows = rows[footer_start:]
        
        # Check if footer has totals
        has_totals = any(
            any(keyword in row['text'].upper() for keyword in ['TOTAL', 'TAX', 'SUBTOTAL'])
            for row in footer_rows
        )
        
        if has_totals:
            sections.append({
                'type': 'footer',
                'start_row': footer_start + 1,
                'end_row': total_rows,
                'rows': footer_rows,
                'description': 'Totals, payment, change'
            })
        
        # Items: Everything between header and footer
        items_rows = rows[header_end:footer_start]
        if items_rows:
            sections.append({
                'type': 'items',
                'start_row': header_end + 1,
                'end_row': footer_start,
                'rows': items_rows,
                'description': 'Line items and products'
            })
        
        return sections
    
    # ==================== MULTI-LINE ITEM MERGING ====================
    
    def _merge_multiline_items(self, rows: List[Dict]) -> List[Dict]:
        """
        Merge multi-line items (long product names split across lines)
        
        Example:
        Row 1: "ORGANIC WHOLE WHEAT"
        Row 2: "BREAD"
        → Merged: "ORGANIC WHOLE WHEAT BREAD"
        """
        if len(rows) <= 1:
            return rows
        
        merged_rows = []
        skip_next = False
        
        for i, row in enumerate(rows):
            if skip_next:
                skip_next = False
                continue
            
            # Check if next row is continuation
            if i < len(rows) - 1:
                next_row = rows[i + 1]
                
                # Heuristic: current has price, next doesn't
                has_price = self._contains_price(row['text'])
                next_has_price = self._contains_price(next_row['text'])
                
                if has_price and not next_has_price:
                    # Check Y distance
                    y_distance = next_row['y_position'] - row['y_position']
                    
                    if y_distance < 40:  # Close enough
                        # Merge
                        merged_text = row['text'] + ' ' + next_row['text']
                        merged_items = row['items'] + next_row['items']
                        merged_conf = (row['confidence'] + next_row['confidence']) / 2
                        
                        merged_rows.append({
                            'row_number': row['row_number'],
                            'text': merged_text,
                            'items': merged_items,
                            'item_count': len(merged_items),
                            'confidence': merged_conf,
                            'y_position': row['y_position'],
                            'merged': True
                        })
                        
                        skip_next = True
                        continue
            
            merged_rows.append(row)
        
        merges = sum(1 for row in merged_rows if row.get('merged', False))
        if merges > 0:
            logger.info(f"Merged {merges} multi-line items")
        
        return merged_rows
    
    def _contains_price(self, text: str) -> bool:
        """Check if text contains price pattern"""
        import re
        return bool(re.search(r'\$\d+\.\d{2}', text))
    
    # ==================== STRUCTURE ANALYSIS ====================
    
    def _analyze_structure(self, rows: List[Dict], sections: List[Dict]) -> Dict:
        """Analyze receipt structure and return statistics"""
        return {
            'total_rows': len(rows),
            'sections_count': len(sections),
            'section_types': [s['type'] for s in sections],
            'has_header': any(s['type'] == 'header' for s in sections),
            'has_footer': any(s['type'] == 'footer' for s in sections),
            'has_items': any(s['type'] == 'items' for s in sections),
            'multi_line_items': sum(1 for row in rows if row.get('merged', False)),
            'rows_with_prices': sum(1 for row in rows if self._contains_price(row['text'])),
            'average_items_per_row': sum(row['item_count'] for row in rows) / len(rows) if rows else 0
        }
    
    # ==================== HELPER METHODS ====================
    
    def _get_y_position(self, line: Dict) -> float:
        """Get Y position (top of text)"""
        bbox = line.get('bbox', [])
        if len(bbox) == 4:
            return (bbox[0][1] + bbox[1][1]) / 2
        return 0
    
    def _get_x_position(self, line: Dict) -> float:
        """Get X position (left of text)"""
        bbox = line.get('bbox', [])
        if len(bbox) == 4:
            return (bbox[0][0] + bbox[3][0]) / 2
        return 0
    
    # ==================== LEGACY SUPPORT ====================
    
    def _format_rows_as_text(self, rows: List[List[Dict]]) -> str:
        """Legacy method for backward compatibility"""
        formatted_lines = []
        for row in rows:
            row_text = ' '.join([item['text'] for item in row])
            formatted_lines.append(row_text)
        return '\n'.join(formatted_lines)
    
    def _create_structured_data(self, rows: List[List[Dict]]) -> List[Dict]:
        """Legacy method for backward compatibility"""
        structured_rows = []
        for i, row in enumerate(rows, 1):
            row_text = ' '.join([item['text'] for item in row])
            confidences = [item['confidence'] for item in row]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            structured_rows.append({
                'row_number': i,
                'text': row_text,
                'items': row,
                'confidence': round(float(avg_confidence), 3)
            })
        
        return structured_rows


# ==================== HELPER FUNCTION ====================

def format_ocr_result(ocr_lines: List[Dict], 
                     row_tolerance: int = 15) -> Dict:
    """
    Quick helper to format OCR results with all optimizations
    
    Args:
        ocr_lines: List of OCR line results
        row_tolerance: Base pixels tolerance (auto-adjusted)
    
    Returns:
        Complete formatted result
    """
    formatter = ReceiptTextFormatter(row_tolerance=row_tolerance)
    return formatter.format_receipt_text(ocr_lines)


# ==================== TESTING ====================

if __name__ == "__main__":
    # Example test
    example_lines = [
        {
            'text': 'WALMART',
            'confidence': 0.99,
            'bbox': [[100, 50], [300, 50], [300, 80], [100, 80]]
        },
        {
            'text': 'SUPERCENTER',
            'confidence': 0.98,
            'bbox': [[320, 50], [500, 50], [500, 80], [320, 80]]
        },
        {
            'text': 'ITEM 1',
            'confidence': 0.95,
            'bbox': [[100, 200], [250, 200], [250, 220], [100, 220]]
        },
        {
            'text': '$5.99',
            'confidence': 0.96,
            'bbox': [[500, 200], [600, 200], [600, 220], [500, 220]]
        },
        {
            'text': 'TOTAL',
            'confidence': 0.97,
            'bbox': [[100, 400], [200, 400], [200, 420], [100, 420]]
        },
        {
            'text': '$5.99',
            'confidence': 0.95,
            'bbox': [[500, 400], [600, 400], [600, 420], [500, 420]]
        }
    ]
    
    print("\n" + "="*60)
    print("OPTIMIZED RECEIPT FORMATTER - Test")
    print("="*60 + "\n")
    
    result = format_ocr_result(example_lines)
    
    print(f"Original lines: {result['original_lines']}")
    print(f"Formatted rows: {result['total_rows']}")
    print(f"Sections: {result['structure']['sections_count']}")
    print(f"\nFormatted Text:")
    print("-" * 60)
    print(result['formatted_text'])
    print("-" * 60)
    
    print(f"\nStructure:")
    for key, value in result['structure'].items():
        print(f"  {key}: {value}")
    
    print(f"\nSections Detected:")
    for section in result['sections']:
        print(f"  {section['type']}: rows {section['start_row']}-{section['end_row']}")
    
    print("\n" + "="*60 + "\n")