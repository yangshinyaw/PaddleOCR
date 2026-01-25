"""
Smart Adaptive Preprocessing
Only applies techniques when they actually improve results
"""

import cv2
import numpy as np
from pathlib import Path
from image_preprocessor import ImagePreprocessor
from ocr_engine import OCREngine


class SmartPreprocessor:
    """
    Intelligently decides which preprocessing to apply
    based on image quality analysis
    """
    
    def __init__(self):
        self.preprocessor = ImagePreprocessor()
        self.ocr = OCREngine()
    
    def analyze_image_quality(self, image_path):
        """
        Analyze image to determine what preprocessing is needed
        
        Returns dict with quality metrics
        """
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        metrics = {}
        
        # 1. Check brightness
        avg_brightness = np.mean(gray)
        metrics['brightness'] = avg_brightness
        metrics['needs_brightness_adjustment'] = avg_brightness < 100 or avg_brightness > 200
        
        # 2. Check contrast
        contrast = gray.std()
        metrics['contrast'] = contrast
        metrics['needs_contrast_boost'] = contrast < 50
        
        # 3. Check blur (Laplacian variance)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        metrics['sharpness'] = laplacian_var
        metrics['needs_sharpening'] = laplacian_var < 100
        
        # 4. Check rotation (detect if image is tilted)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
        
        if lines is not None and len(lines) > 0:
            angles = []
            for line in lines[:50]:
                angle = np.degrees(line[0][1]) - 90
                if -45 < angle < 45:
                    angles.append(angle)
            
            if angles:
                median_angle = np.median(angles)
                metrics['rotation_angle'] = median_angle
                metrics['needs_rotation'] = abs(median_angle) > 1.0
            else:
                metrics['rotation_angle'] = 0
                metrics['needs_rotation'] = False
        else:
            metrics['rotation_angle'] = 0
            metrics['needs_rotation'] = False
        
        # 5. Check for noise
        # Simple noise estimation using local variance
        kernel_size = 5
        kernel = np.ones((kernel_size, kernel_size), np.float32) / (kernel_size * kernel_size)
        local_mean = cv2.filter2D(gray.astype(float), -1, kernel)
        local_var = cv2.filter2D((gray.astype(float) - local_mean) ** 2, -1, kernel)
        noise_level = np.mean(local_var)
        
        metrics['noise_level'] = noise_level
        metrics['needs_denoising'] = noise_level > 100
        
        return metrics
    
    def smart_preprocess(self, image_path, output_path=None):
        """
        Apply only the preprocessing techniques that are needed
        """
        print(f"\n{'='*60}")
        print("Smart Preprocessing Analysis")
        print(f"{'='*60}\n")
        
        # Analyze image
        metrics = self.analyze_image_quality(image_path)
        
        print("Image Quality Metrics:")
        print(f"  Brightness: {metrics['brightness']:.1f} (optimal: 100-200)")
        print(f"  Contrast: {metrics['contrast']:.1f} (optimal: >50)")
        print(f"  Sharpness: {metrics['sharpness']:.1f} (optimal: >100)")
        print(f"  Rotation: {metrics['rotation_angle']:.2f}° (optimal: ~0)")
        print(f"  Noise Level: {metrics['noise_level']:.1f} (optimal: <100)")
        
        print(f"\nRecommended Preprocessing:")
        
        # Load image
        img = cv2.imread(image_path)
        applied_techniques = []
        
        # Apply only needed techniques
        
        # 1. Rotation (if needed)
        if metrics['needs_rotation']:
            print(f"  ✅ Rotation correction ({metrics['rotation_angle']:.2f}°)")
            img = self.preprocessor._rotate_image(img, metrics['rotation_angle'])
            applied_techniques.append('rotation')
        else:
            print(f"  ⏭️  Skip rotation (image is straight)")
        
        # 2. Denoising (if needed)
        if metrics['needs_denoising']:
            print(f"  ✅ Denoising (noise level: {metrics['noise_level']:.1f})")
            img = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
            applied_techniques.append('denoising')
        else:
            print(f"  ⏭️  Skip denoising (image is clean)")
        
        # 3. Contrast (if needed)
        if metrics['needs_contrast_boost']:
            print(f"  ✅ Contrast enhancement (current: {metrics['contrast']:.1f})")
            img = self.preprocessor._enhance_contrast(img)
            applied_techniques.append('contrast')
        else:
            print(f"  ⏭️  Skip contrast (already good)")
        
        # 4. Sharpening (if needed)
        if metrics['needs_sharpening']:
            print(f"  ✅ Sharpening (current: {metrics['sharpness']:.1f})")
            img = self.preprocessor._sharpen(img)
            applied_techniques.append('sharpening')
        else:
            print(f"  ⏭️  Skip sharpening (already sharp)")
        
        # Save result
        if output_path is None:
            output_dir = Path("data/temp")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"smart_{Path(image_path).name}"
        
        cv2.imwrite(str(output_path), img)
        
        print(f"\n✅ Applied: {', '.join(applied_techniques) if applied_techniques else 'None (image is already optimal!)'}")
        print(f"✅ Saved to: {output_path}\n")
        
        return str(output_path), metrics, applied_techniques
    
    def compare_preprocessing_strategies(self, image_path):
        """
        Compare different preprocessing strategies and pick the best
        """
        print(f"\n{'='*60}")
        print("Comparing Preprocessing Strategies")
        print(f"{'='*60}\n")
        
        results = {}
        
        # Strategy 1: No preprocessing
        print("1. Testing without preprocessing...")
        result_none = self.ocr.extract_text(image_path)
        results['No Preprocessing'] = {
            'confidence': result_none['average_confidence'],
            'lines': result_none['lines_detected'],
            'time': result_none['processing_time_ms'],
            'path': image_path
        }
        print(f"   Confidence: {result_none['average_confidence']:.1%}")
        
        # Strategy 2: Full preprocessing
        print("\n2. Testing with full preprocessing...")
        full_path = self.preprocessor.preprocess(image_path)
        result_full = self.ocr.extract_text(full_path)
        results['Full Preprocessing'] = {
            'confidence': result_full['average_confidence'],
            'lines': result_full['lines_detected'],
            'time': result_full['processing_time_ms'],
            'path': full_path
        }
        print(f"   Confidence: {result_full['average_confidence']:.1%}")
        
        # Strategy 3: Smart preprocessing
        print("\n3. Testing with smart preprocessing...")
        smart_path, metrics, techniques = self.smart_preprocess(image_path)
        result_smart = self.ocr.extract_text(smart_path)
        results['Smart Preprocessing'] = {
            'confidence': result_smart['average_confidence'],
            'lines': result_smart['lines_detected'],
            'time': result_smart['processing_time_ms'],
            'path': smart_path,
            'techniques': techniques
        }
        print(f"   Confidence: {result_smart['average_confidence']:.1%}")
        
        # Find best strategy
        print(f"\n{'='*60}")
        print("Results Comparison")
        print(f"{'='*60}\n")
        
        sorted_results = sorted(results.items(), key=lambda x: x[1]['confidence'], reverse=True)
        
        for i, (strategy, data) in enumerate(sorted_results, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
            print(f"{medal} {i}. {strategy}")
            print(f"     Confidence: {data['confidence']:.1%}")
            print(f"     Lines: {data['lines']}")
            print(f"     Time: {data['time']}ms")
            if 'techniques' in data:
                print(f"     Applied: {', '.join(data['techniques']) if data['techniques'] else 'None'}")
        
        best_strategy = sorted_results[0][0]
        best_confidence = sorted_results[0][1]['confidence']
        
        print(f"\n✅ Winner: {best_strategy} ({best_confidence:.1%})")
        print(f"{'='*60}\n")
        
        return sorted_results[0]


def main():
    """Test smart preprocessing"""
    smart = SmartPreprocessor()
    
    # Find sample images
    sample_dir = Path("data/sample_receipts")
    images = list(sample_dir.glob("*.jpg")) + list(sample_dir.glob("*.png"))
    
    if not images:
        print("No sample images found!")
        return
    
    for img_path in images:
        print(f"\n{'#'*70}")
        print(f"# Testing: {img_path.name}")
        print(f"{'#'*70}")
        
        best_strategy, result = smart.compare_preprocessing_strategies(str(img_path))
        
        print(f"\n🎯 Recommendation for {img_path.name}:")
        print(f"   Use: {best_strategy}")
        print(f"   Expected confidence: {result['confidence']:.1%}")


if __name__ == "__main__":
    main()
