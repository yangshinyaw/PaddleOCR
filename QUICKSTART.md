# 🚀 Quick Start Guide - Week 1

---

## Prerequisites

- **Python 3.10+** installed
- **pip** package manager
- **Git** (optional, for version control)
- **GPU** (recommended but not required)
  - NVIDIA GPU with CUDA support for best performance
  - CPU will work but ~10x slower

---

## Step 1: Setup Environment

### Clone/Download Project
```bash
cd /path/to/your/workspace
# If you have the project files, cd into the directory
cd receipt-ocr-api
```

### Create Virtual Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate it
# On Linux/Mac:
source venv/bin/activate

# On Windows:
# venv\Scripts\activate
```

### Install Dependencies
```bash
# Install all required packages
pip install -r requirements.txt

# This will take a few minutes (downloading models)
```

---

## Step 2: Verify Installation

Run the installation test:

```bash
python src/test_paddle_install.py
```

**Expected output:**
```
Testing PaddleOCR Installation...
============================================================

1. Testing PaddleOCR import...
   ✅ PaddleOCR imported successfully

2. Testing OpenCV import...
   ✅ OpenCV imported successfully (version 4.8.1)

3. Testing NumPy import...
   ✅ NumPy imported successfully (version 1.24.3)

4. Checking GPU availability...
   ✅ PaddlePaddle compiled with CUDA support
   ℹ️  GPUs available: 1
   🚀 GPU acceleration available!

5. Testing OCR initialization...
   ✅ PaddleOCR initialized successfully

6. Checking additional dependencies...
   ✅ Pillow
   ✅ PyYAML
   ✅ loguru

============================================================
INSTALLATION CHECK COMPLETE
✅ All systems ready! You can now run the OCR engine.
```

---

## Step 3: Add Sample Images

Add some receipt images for testing:

```bash
# Put your receipt images here
data/sample_receipts/
```

**Tips for good test images:**
- Clear, well-lit photos
- Receipt fully visible
- No excessive shadows
- Various orientations (to test auto-rotation)
- Different stores/formats

**Don't have receipts?**
- Take photos of receipts with your phone
- Download sample receipts from Google Images
- Ask colleagues for test data

---

## Step 4: Test OCR Engine

Run the OCR engine with your sample images:

```bash
python src/ocr_engine.py
```

**What happens:**
1. Loads first image from `data/sample_receipts/`
2. Validates the image
3. Extracts text using PaddleOCR
4. Displays results with confidence scores

**Example output:**
```
============================================================
Receipt OCR Engine - Test Run
============================================================

Found 3 sample image(s)

Testing with: data/sample_receipts/walmart_receipt.jpg

Image validation: ✅ Valid image

Extracting text...

============================================================
RESULTS
============================================================

Status: success
Lines detected: 24
Processing time: 287ms
Average confidence: 96.3%

Extracted Text:
------------------------------------------------------------
 1. [98.2%] WALMART SUPERCENTER
 2. [97.5%] 123 MAIN STREET
 3. [95.1%] ANYTOWN, ST 12345
 4. [96.8%] Date: 01/15/2024
 5. [94.2%] Item 1          $5.99
...
```

---

## Step 5: Test Preprocessing

Test image enhancement:

```bash
python src/image_preprocessor.py
```

**What it does:**
- Auto-rotates tilted images
- Removes noise
- Enhances contrast
- Sharpens text
- Saves processed images to `data/temp/`

**Compare before/after:**
- Original: `data/sample_receipts/your_image.jpg`
- Processed: `data/temp/preprocessed_your_image.jpg`

---

## Step 6: Test Image Stitching

For long receipts (2+ parts):

```bash
python src/image_stitcher.py
```

**Requirements:**
- At least 2 images in `data/sample_receipts/`
- Images should be parts of the same receipt (or any overlapping images)

**What it does:**
- Detects features in both images
- Finds overlapping regions
- Stitches images together
- Blends edges for seamless result
- Saves to `data/temp/stitched_receipt.jpg`

---

## Step 7: Test Complete Pipeline

Run the integrated pipeline:

```bash
python src/receipt_processor.py
```

**What it does:**
1. Preprocesses images (enhance, rotate)
2. Stitches multiple parts (if applicable)
3. Extracts text with OCR
4. Parses metadata (merchant, total, date)
5. Displays comprehensive results

**Example output:**
```
============================================================
Receipt Processing Pipeline - Demo
============================================================

Demo 1: Single Image Processing
============================================================

Processing: walmart_receipt.jpg

Status: success
Lines detected: 24
Processing time: 312ms
Average confidence: 96.3%

Extracted Metadata:
  merchant_name: WALMART SUPERCENTER
  total: 45.67
  date: 01/15/2024
  items_count: 0
```

---

## Step 8: Run Tests

Verify everything works:

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_ocr_engine.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

---

## Common Issues & Solutions

### Issue 1: "ModuleNotFoundError: No module named 'paddleocr'"
**Solution:**
```bash
pip install paddlepaddle-gpu paddleocr
```

### Issue 2: "GPU not available" warning
**Solution:** This is OK! OCR will use CPU (just slower). If you want GPU:
1. Install CUDA toolkit
2. Install `paddlepaddle-gpu` instead of `paddlepaddle`
3. Verify with `nvidia-smi`

### Issue 3: "No sample images found"
**Solution:** Add images to `data/sample_receipts/`:
```bash
# Example
cp ~/Downloads/receipt.jpg data/sample_receipts/
```

### Issue 4: OCR accuracy is low
**Solution:** Try preprocessing first:
```python
from receipt_processor import ReceiptProcessor
processor = ReceiptProcessor()
result = processor.process_single_image('image.jpg', preprocess=True)
```

### Issue 5: "ModuleNotFoundError: No module named 'magic'"
**Solution:**
```bash
pip install python-magic
# On Windows, may also need:
pip install python-magic-bin
```

---

## Development Workflow

### Daily Workflow
1. **Morning:** Review `docs/week1_progress.md`
2. **Code:** Work on assigned tasks
3. **Test:** Run relevant tests
4. **Document:** Update progress doc
5. **Commit:** Save your work

### Testing New Changes
```bash
# 1. Make changes to code
# 2. Test specific module
python src/your_module.py

# 3. Run unit tests
pytest tests/test_your_module.py

# 4. Test integration
python src/receipt_processor.py

# 5. Verify nothing broke
pytest tests/ -v
```

---

## Project Structure Quick Reference

```
receipt-ocr-api/
├── src/                        # Source code
│   ├── ocr_engine.py          # Core OCR functionality
│   ├── image_preprocessor.py  # Image enhancement
│   ├── image_stitcher.py      # Long receipt stitching
│   ├── receipt_processor.py   # Integrated pipeline
│   ├── utils.py               # Helper functions
│   └── test_paddle_install.py # Installation verification
├── tests/                      # Test files
│   └── test_ocr_engine.py     # OCR tests
├── data/
│   ├── sample_receipts/       # PUT TEST IMAGES HERE
│   └── temp/                  # Processed images (auto-generated)
├── config/
│   └── ocr_config.yaml        # Configuration
├── docs/
│   └── week1_progress.md      # Progress tracking
├── requirements.txt            # Dependencies
└── README.md                   # Project overview
```

---

## Next Steps

### After Week 1 Setup:
1. ✅ Collect 50+ sample receipts for testing
2. ✅ Run benchmarks (accuracy, speed)
3. ✅ Document edge cases
4. ✅ Complete all Week 1 tasks
5. ➡️ Move to Week 2 (FastAPI development)

### Week 2 Preview:
- Build REST API with FastAPI
- Add file upload endpoints
- Implement API key system
- Create rate limiting
- Set up error handling

---

## Getting Help

### Documentation
- Check `docs/week1_progress.md` for detailed task breakdown
- Review `config/ocr_config.yaml` for configuration options
- Read inline code comments

### Debugging
```bash
# Enable debug logging
# Edit your Python file:
setup_logging(level="DEBUG")

# Check logs
tail -f logs/receipt_ocr.log
```

### Performance Tuning
```yaml
# Edit config/ocr_config.yaml
ocr:
  use_gpu: true              # Use GPU if available
  det_db_thresh: 0.3         # Lower = more sensitive (slower)
  rec_batch_num: 6           # Batch size (higher = faster but more memory)
```

---

## Quick Commands Cheat Sheet

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Verify installation
python src/test_paddle_install.py

# Test components
python src/ocr_engine.py
python src/image_preprocessor.py
python src/image_stitcher.py
python src/receipt_processor.py

# Run tests
pytest tests/ -v

# Clean up temp files
rm -rf data/temp/*

# Check logs
tail -f logs/receipt_ocr.log
```

---

**Ready to start building? Let's go! 🚀**

Questions? Check `docs/week1_progress.md` or review the code comments.