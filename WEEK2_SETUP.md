# Week 2 Setup Guide - Complete Instructions

## 📦 Step 1: Install Week 2 Dependencies

Open PowerShell in your project folder and run:

```powershell
cd C:\receipt-ocr-api

# Activate your virtual environment
.\venv\Scripts\Activate

# Install Week 2 dependencies
pip install -r requirements-week2.txt
```

This installs:
- ✅ FastAPI (web framework)
- ✅ Uvicorn (ASGI server)
- ✅ Pydantic (data validation)
- ✅ pytest (testing)

---

## 📁 Step 2: Verify File Structure

Your project should now have:

```
receipt-ocr-api/
├── main.py                    # ✅ NEW: FastAPI app entry point
├── src/
│   ├── api/                   # ✅ NEW: API layer
│   │   ├── __init__.py
│   │   ├── models.py          # Request/Response models
│   │   └── routes.py          # API endpoints
│   ├── ocr_engine.py          # (existing)
│   ├── image_preprocessor.py  # (existing)
│   ├── receipt_processor.py   # (existing)
│   └── utils.py               # (existing)
├── tests/
│   └── test_api.py            # ✅ NEW: API tests
├── requirements-week2.txt      # ✅ NEW: Week 2 dependencies
└── ... (other existing files)
```

---

## 🚀 Step 3: Start the API Server

Run this command:

```powershell
python main.py
```

OR:

```powershell
uvicorn main:app --reload
```

You should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

✅ Your API is now running!

---

## 📚 Step 4: View API Documentation

Open your web browser and go to:

**Swagger UI (Interactive):**
```
http://localhost:8000/docs
```

**ReDoc (Alternative):**
```
http://localhost:8000/redoc
```

You'll see:
- ✅ All API endpoints listed
- ✅ Try them out directly in browser
- ✅ See request/response examples

---

## 🧪 Step 5: Test the API

### Method 1: Using Web Browser (Easiest)

1. Go to `http://localhost:8000/docs`
2. Click on `POST /api/v1/ocr/scan`
3. Click "Try it out"
4. Click "Choose File" and select a receipt image
5. Click "Execute"
6. See the result!

### Method 2: Using PowerShell (curl)

```powershell
# Test health check
curl http://localhost:8000/health

# Test OCR scan
curl -X POST http://localhost:8000/api/v1/ocr/scan `
  -F "file=@data\sample_receipts\receipt.jpg" `
  -F "preprocess=true"
```

### Method 3: Using Python Test Script

```powershell
# Run automated tests
python tests\test_api.py
```

You should see:
```
Testing: Root endpoint... ✅ PASSED
Testing: Health check... ✅ PASSED
Testing: Scan receipt... ✅ PASSED
...
```

### Method 4: Using Postman

1. Download Postman: https://www.postman.com/downloads/
2. Create new request
3. Set method to `POST`
4. URL: `http://localhost:8000/api/v1/ocr/scan`
5. Go to "Body" → "form-data"
6. Add key `file` (type: File) → Select receipt image
7. Add key `preprocess` (type: Text) → Value: `true`
8. Click "Send"

---

## 📋 Available Endpoints

### 1. **Health Check**
```
GET /health
```
Check if API is running

### 2. **Simple OCR Scan**
```
POST /api/v1/ocr/scan
```
Upload 1 receipt, get text

### 3. **OCR with Metadata**
```
POST /api/v1/ocr/scan-with-metadata
```
Get merchant name, date, total

### 4. **Multiple Images (Stitching)**
```
POST /api/v1/ocr/scan-multiple
```
Upload 2-10 images, stitch together

### 5. **Batch Processing**
```
POST /api/v1/ocr/batch
```
Process multiple separate receipts

---

## 🎯 Quick Test Examples

### Example 1: Simple Scan

```bash
curl -X POST http://localhost:8000/api/v1/ocr/scan \
  -F "file=@receipt.jpg"
```

Response:
```json
{
  "status": "success",
  "filename": "receipt.jpg",
  "text": "WALMART\nReceipt #12345\nTotal: $45.99",
  "confidence": 0.963,
  "lines_detected": 65,
  "processing_time_ms": 1250
}
```

### Example 2: With Metadata

```bash
curl -X POST http://localhost:8000/api/v1/ocr/scan-with-metadata \
  -F "file=@receipt.jpg"
```

Response:
```json
{
  "status": "success",
  "filename": "receipt.jpg",
  "text": "WALMART...",
  "confidence": 0.963,
  "merchant_name": "WALMART",
  "date": "01/28/2026",
  "total": "$45.99"
}
```

---

## ❌ Troubleshooting

### Issue 1: "Module not found" error

```powershell
# Make sure you're in the right directory
cd C:\receipt-ocr-api

# Make sure virtual environment is activated
.\venv\Scripts\Activate

# Reinstall dependencies
pip install -r requirements-week2.txt
```

### Issue 2: "Port already in use"

```powershell
# Use different port
uvicorn main:app --reload --port 8001
```

Then access at `http://localhost:8001`

### Issue 3: Can't access from browser

Make sure:
- ✅ Server is running (see console output)
- ✅ Using correct URL: `http://localhost:8000`
- ✅ No firewall blocking

---

## 🎓 Learning the API

### Step-by-Step Tutorial:

1. **Start server:**
   ```powershell
   python main.py
   ```

2. **Open docs:**
   ```
   http://localhost:8000/docs
   ```

3. **Try health check:**
   - Click on `GET /health`
   - Click "Try it out"
   - Click "Execute"
   - See response!

4. **Upload a receipt:**
   - Click on `POST /api/v1/ocr/scan`
   - Click "Try it out"
   - Choose a receipt image
   - Set `preprocess` to `true`
   - Click "Execute"
   - See extracted text!

5. **Test different endpoints:**
   - Try `/api/v1/ocr/scan-with-metadata`
   - Try uploading multiple images
   - Experiment!

---

## 📊 Success Checklist

After setup, you should be able to:

- ✅ Start API server: `python main.py`
- ✅ See API docs at `http://localhost:8000/docs`
- ✅ Upload receipt via browser interface
- ✅ Get JSON response with extracted text
- ✅ See confidence scores for each line
- ✅ Extract metadata (merchant, date, total)
- ✅ Process multiple images
- ✅ Run automated tests successfully

---

## 🎉 Next Steps

Once everything works:

1. ✅ Test with different receipt images
2. ✅ Try all 5 endpoints
3. ✅ Read the API documentation
4. ✅ Experiment with parameters
5. ✅ Build a simple frontend (Week 3?)

---

## 💡 Tips

- **Keep server running**: Don't close the PowerShell window
- **Auto-reload**: Server automatically reloads when you edit code
- **Check logs**: Server shows what's happening in console
- **Use docs**: The `/docs` page is your best friend!

---

## 🆘 Need Help?

If something doesn't work:

1. Check server is running (look at PowerShell window)
2. Check URL is correct (`http://localhost:8000`)
3. Check file path is correct
4. Look at server logs for errors
5. Try running tests: `python tests\test_api.py`

---

**You're ready to use your Receipt OCR API!** 🚀
