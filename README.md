# Receipt OCR API - Week 1 Development

## Overview
Building the core OCR engine with PaddleOCR for high-accuracy receipt text extraction.

## Week 1 Goals
- ✅ Day 1-2: PaddleOCR setup and basic testing
- ✅ Day 3-4: Image preprocessing pipeline
- ✅ Day 5-7: Image stitching for long receipts

## Setup Instructions

### 1. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Verify PaddleOCR Installation
```bash
python src/test_paddle_install.py
```

### 4. Test with Sample Receipt
```bash
python src/ocr_engine.py
```

## Project Structure
```
receipt-ocr-api/
├── src/
│   ├── ocr_engine.py          # Core PaddleOCR wrapper
│   ├── image_preprocessor.py  # Image enhancement & preprocessing
│   ├── image_stitcher.py      # Long receipt stitching
│   └── utils.py               # Helper functions
├── tests/
│   ├── test_ocr_engine.py
│   ├── test_preprocessor.py
│   └── test_stitcher.py
├── data/
│   ├── sample_receipts/       # Test images
│   └── temp/                  # Temporary processing files
├── config/
│   └── ocr_config.yaml        # OCR configuration
└── docs/
    └── week1_progress.md      # Daily progress tracking
```

## Current Status
- [ ] PaddleOCR installed and tested
- [ ] Basic OCR extraction working
- [ ] Image preprocessing pipeline
- [ ] Image stitching for long receipts

## Next Steps
See `docs/week1_progress.md` for detailed daily tasks and progress.