"""
Multi-Pass OCR with Voting
Runs OCR multiple times and picks the most confident results
"""

from ocr_engine import OCREngine
from image_preprocessor import ImagePreprocessor
from pathlib import Path
from collections import Counter


class MultiPassOCR:
    """
    Run OCR multiple times with different settings and combine results
    """
    
    def __init__(self):
        self.ocr = OCREngine()
        self.preprocessor = ImagePreprocessor()
    
    def extract_with_voting(self, image_path, num_passes=3):
        """
        Run OCR multiple times and use voting to pick best results
        
        Args:
            image_path: Path to image
            num_passes: Number of OCR passes to run
        
        Returns:
            Combined results with highest confidence
        """
        print(f"\n{'='*60}")
        print(f"Multi-Pass OCR (${num_passes} passes)")
        print(f"{'='*60}\n")
        
        all_results = []
        
        # Pass 1: Original image
        print("Pass 1: Original image...")
        result1 = self.ocr.extract_text(image_path)
        all_results.append(result1)
        print(f"  Confidence: {result1['average_confidence']:.1%}, Lines: {result1['lines_detected']}")
        
        # Pass 2: Preprocessed image
        print("\nPass 2: With preprocessing...")
        preprocessed = self.preprocessor.preprocess(image_path)
        result2 = self.ocr.extract_text(preprocessed)
        all_results.append(result2)
        print(f"  Confidence: {result2['average_confidence']:.1%}, Lines: {result2['lines_detected']}")
        
        # Pass 3: Grayscale
        print("\nPass 3: Grayscale...")
        gray = self.preprocessor.convert_to_grayscale(image_path)
        result3 = self.ocr.extract_text(gray)
        all_results.append(result3)
        print(f"  Confidence: {result3['average_confidence']:.1%}, Lines: {result3['lines_detected']}")
        
        # Combine results using voting
        print(f"\n{'='*60}")
        print("Combining Results with Voting")
        print(f"{'='*60}\n")
        
        # Group similar text lines
        combined_lines = self._vote_on_results(all_results)
        
        # Calculate new average confidence
        avg_confidence = sum(line['confidence'] for line in combined_lines) / len(combined_lines) if combined_lines else 0
        
        result = {
            'status': 'success',
            'lines_detected': len(combined_lines),
            'average_confidence': avg_confidence,
            'lines': combined_lines,
            'method': f'multi-pass-{num_passes}'
        }
        
        print(f"Final Result:")
        print(f"  Lines: {len(combined_lines)}")
        print(f"  Average Confidence: {avg_confidence:.1%}")
        print(f"{'='*60}\n")
        
        return result
    
    def _vote_on_results(self, all_results):
        """
        Combine multiple OCR results using voting
        Pick the version of each line with highest confidence
        """
        # Create a dictionary to store all versions of each line
        line_versions = {}
        
        for result_idx, result in enumerate(all_results):
            if result['status'] != 'success':
                continue
            
            for line in result['lines']:
                text = line['text'].strip().lower()
                
                if text not in line_versions:
                    line_versions[text] = []
                
                line_versions[text].append({
                    'original_text': line['text'],
                    'confidence': line['confidence'],
                    'source': result_idx
                })
        
        # For each unique line, pick the version with highest confidence
        combined_lines = []
        
        for text, versions in line_versions.items():
            # Pick version with highest confidence
            best_version = max(versions, key=lambda x: x['confidence'])
            
            combined_lines.append({
                'text': best_version['original_text'],
                'confidence': best_version['confidence'],
                'votes': len(versions)  # How many passes detected this line
            })
        
        # Sort by original position (approximate)
        return combined_lines


def main():
    """Test multi-pass OCR"""
    multi_pass = MultiPassOCR()
    
    sample_dir = Path("data/sample_receipts")
    images = list(sample_dir.glob("*.jpg")) + list(sample_dir.glob("*.png"))
    
    if not images:
        print("No sample images found!")
        return
    
    test_image = str(images[0])
    
    print(f"\nTesting: {Path(test_image).name}\n")
    
    # Regular OCR
    print("="*60)
    print("Regular Single-Pass OCR")
    print("="*60)
    ocr = OCREngine()
    regular_result = ocr.extract_text(test_image)
    print(f"Confidence: {regular_result['average_confidence']:.1%}")
    print(f"Lines: {regular_result['lines_detected']}\n")
    
    # Multi-pass OCR
    result = multi_pass.extract_with_voting(test_image)
    
    # Compare
    print("\n" + "="*60)
    print("Comparison")
    print("="*60)
    print(f"Regular OCR:    {regular_result['average_confidence']:.1%} confidence")
    print(f"Multi-Pass OCR: {result['average_confidence']:.1%} confidence")
    
    improvement = result['average_confidence'] - regular_result['average_confidence']
    if improvement > 0:
        print(f"\n✅ Improvement: +{improvement:.1%}")
    else:
        print(f"\n➡️  No significant improvement")


if __name__ == "__main__":
    main()
