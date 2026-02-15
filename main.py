"""
Receipt OCR API - Main Application
FastAPI application for receipt text extraction

Run with: python main.py
Access web app at: http://localhost:8000 (or https:// if certificates exist)
Access API docs at: http://localhost:8000/docs
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from api.routes import router

# Create FastAPI app
app = FastAPI(
    title="Receipt OCR API",
    description="Extract text from receipt images using PaddleOCR",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for web app
webapp_path = Path(__file__).parent / "webapp"
if webapp_path.exists():
    app.mount("/static", StaticFiles(directory=str(webapp_path)), name="static")

# Include API routes
app.include_router(router, prefix="/api/v1")

@app.get("/", tags=["Root"])
async def root():
    """Serve the web application"""
    webapp_file = Path(__file__).parent / "webapp" / "index.html"
    if webapp_file.exists():
        return FileResponse(webapp_file)
    return {
        "message": "Receipt OCR API",
        "version": "1.0.0",
        "webapp": "Web app not found. Check /webapp folder.",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "receipt-ocr-api",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    from pathlib import Path
    
    # Check if SSL certificates exist
    cert_file = Path("cert.pem")
    key_file = Path("key.pem")
    
    if cert_file.exists() and key_file.exists():
        print("=" * 60)
        print("🔒 HTTPS ENABLED - Camera will work on mobile!")
        print("=" * 60)
        print("📱 Access from mobile: https://192.168.100.160:8000")
        print("⚠️  Accept security warning (self-signed certificate)")
        print("✅ Visual guides will work!")
        print("=" * 60)
        print()
        
        uvicorn.run(
            "main:app", 
            host="0.0.0.0", 
            port=8000, 
            reload=True,
            ssl_keyfile="key.pem",
            ssl_certfile="cert.pem"
        )
    else:
        print("=" * 60)
        print("⚠️  HTTP MODE - Camera won't work on mobile")
        print("=" * 60)
        print("📱 Access: http://192.168.100.160:8000")
        print("💡 Camera requires HTTPS. Use Upload instead.")
        print("🔧 To enable HTTPS, run this command:")
        print('   python -c "from OpenSSL import crypto; k = crypto.PKey(); k.generate_key(crypto.TYPE_RSA, 4096); cert = crypto.X509(); cert.get_subject().CN = \'receipt-ocr\'; cert.set_serial_number(1000); cert.gmtime_adj_notBefore(0); cert.gmtime_adj_notAfter(365*24*60*60); cert.set_issuer(cert.get_subject()); cert.set_pubkey(k); cert.sign(k, \'sha256\'); open(\'cert.pem\', \'wb\').write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert)); open(\'key.pem\', \'wb\').write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))"')
        print("=" * 60)
        print()
        
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)