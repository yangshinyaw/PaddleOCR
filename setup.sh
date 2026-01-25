#!/bin/bash

# Receipt OCR API - Week 1 Setup Script
# This script automates the initial setup process

set -e  # Exit on error

echo "=================================================="
echo "Receipt OCR API - Week 1 Setup"
echo "=================================================="
echo ""

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | grep -oP '(?<=Python )\d+\.\d+')
required_version="3.10"

if (( $(echo "$python_version < $required_version" | bc -l) )); then
    echo -e "${RED}✗ Python $required_version+ required, found $python_version${NC}"
    exit 1
else
    echo -e "${GREEN}✓ Python $python_version${NC}"
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ -d "venv" ]; then
    echo -e "${YELLOW}⚠ Virtual environment already exists, skipping${NC}"
else
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1
echo -e "${GREEN}✓ pip upgraded${NC}"

# Install dependencies
echo ""
echo "Installing dependencies (this may take a few minutes)..."
echo "Installing core packages..."
pip install -q paddlepaddle-gpu==2.6.0 || pip install -q paddlepaddle==2.6.0
pip install -q paddleocr==2.7.3
pip install -q opencv-python==4.8.1.78
pip install -q Pillow==10.1.0

echo "Installing additional packages..."
pip install -q -r requirements.txt

echo -e "${GREEN}✓ All dependencies installed${NC}"

# Create necessary directories
echo ""
echo "Creating project directories..."
mkdir -p data/sample_receipts
mkdir -p data/temp
mkdir -p logs
mkdir -p config
mkdir -p docs
mkdir -p tests
echo -e "${GREEN}✓ Directories created${NC}"

# Verify installation
echo ""
echo "Verifying PaddleOCR installation..."
python3 src/test_paddle_install.py

# Check for sample images
echo ""
echo "Checking for sample images..."
sample_count=$(find data/sample_receipts -name "*.jpg" -o -name "*.png" 2>/dev/null | wc -l)

if [ "$sample_count" -eq 0 ]; then
    echo -e "${YELLOW}⚠ No sample images found${NC}"
    echo "Please add some receipt images to data/sample_receipts/"
    echo ""
    echo "You can:"
    echo "  1. Take photos of receipts with your phone"
    echo "  2. Download sample receipts from Google Images"
    echo "  3. Use existing receipt images you have"
else
    echo -e "${GREEN}✓ Found $sample_count sample image(s)${NC}"
fi

# Setup complete
echo ""
echo "=================================================="
echo -e "${GREEN}Setup Complete!${NC}"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Activate the virtual environment:"
echo "     source venv/bin/activate"
echo ""
echo "  2. Add sample receipt images to:"
echo "     data/sample_receipts/"
echo ""
echo "  3. Test the OCR engine:"
echo "     python src/ocr_engine.py"
echo ""
echo "  4. Test the complete pipeline:"
echo "     python src/receipt_processor.py"
echo ""
echo "  5. Read the Quick Start Guide:"
echo "     cat QUICKSTART.md"
echo ""
echo "Happy coding! 🚀"
echo ""