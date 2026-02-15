// Global state
let currentFile = null;
let currentResults = null;
let videoStream = null;
let currentTab = 'formatted';
let edgeDetector = null;
let detectedCorners = null;

// Multi-image state
let multiImageMode = false;
let capturedImages = [];
let currentImageIndex = 0;

// API Configuration
// Automatically use the same protocol (http or https) as the current page
const API_BASE_URL = `${window.location.protocol}//${window.location.hostname}:8000`;

/**
 * Toggle multi-image mode
 */
function toggleMultiImageMode() {
    const toggle = document.getElementById('multiImageToggle');
    multiImageMode = toggle.checked;
    
    console.log('📸 Multi-image mode:', multiImageMode ? 'ON' : 'OFF');
    
    if (multiImageMode) {
        capturedImages = [];
        currentImageIndex = 0;
        showMultiImageStatus();
    } else {
        hideMultiImageStatus();
    }
}

/**
 * Show multi-image status bar
 */
function showMultiImageStatus() {
    let statusBar = document.getElementById('multiImageStatus');
    
    if (!statusBar) {
        // Create status bar
        const uploadSection = document.getElementById('uploadSection');
        statusBar = document.createElement('div');
        statusBar.id = 'multiImageStatus';
        statusBar.className = 'multi-image-status active';
        uploadSection.appendChild(statusBar);
    }
    
    updateMultiImageStatus();
}

/**
 * Update multi-image status display
 */
function updateMultiImageStatus() {
    const statusBar = document.getElementById('multiImageStatus');
    if (!statusBar) return;
    
    const imageCount = capturedImages.length;
    
    statusBar.innerHTML = `
        <h4>📸 Multi-Image Mode Active</h4>
        <p>Capture multiple parts of a long receipt. They will be stitched together automatically.</p>
        <div class="image-counter">
            ${imageCount} image${imageCount !== 1 ? 's' : ''} captured
        </div>
        
        ${imageCount > 0 ? `
            <div class="captured-images-grid">
                ${capturedImages.map((img, index) => `
                    <div class="captured-image-item">
                        <img src="${img.url}" alt="Image ${index + 1}">
                        <button class="remove-btn" onclick="removeImage(${index})" title="Remove">×</button>
                        <div class="image-number">${index + 1}</div>
                    </div>
                `).join('')}
            </div>
        ` : ''}
        
        <div class="action-buttons" style="margin-top: 15px;">
            ${imageCount >= 2 ? `
                <button class="btn btn-success" onclick="processMultipleImages()">
                    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
                    </svg>
                    Stitch & Process (${imageCount} images)
                </button>
            ` : ''}
            ${imageCount > 0 ? `
                <button class="btn btn-secondary" onclick="clearCapturedImages()">
                    Clear All
                </button>
            ` : ''}
        </div>
    `;
    
    statusBar.classList.add('active');
}

/**
 * Hide multi-image status
 */
function hideMultiImageStatus() {
    const statusBar = document.getElementById('multiImageStatus');
    if (statusBar) {
        statusBar.classList.remove('active');
    }
}

/**
 * Remove image from captured images
 */
function removeImage(index) {
    console.log(`🗑️ Removing image ${index + 1}`);
    
    // Revoke URL to free memory
    URL.revokeObjectURL(capturedImages[index].url);
    
    // Remove from array
    capturedImages.splice(index, 1);
    
    updateMultiImageStatus();
}

/**
 * Clear all captured images
 */
function clearCapturedImages() {
    console.log('🗑️ Clearing all captured images');
    
    // Revoke all URLs
    capturedImages.forEach(img => URL.revokeObjectURL(img.url));
    
    // Clear array
    capturedImages = [];
    currentImageIndex = 0;
    
    updateMultiImageStatus();
}

// ==================== UPLOAD METHOD SELECTION ====================

function selectUploadMethod(method) {
    const uploadMethod = document.getElementById('uploadMethod');
    const cameraMethod = document.getElementById('cameraMethod');
    const cameraContainer = document.getElementById('cameraContainer');
    const fileInput = document.getElementById('fileInput');

    if (method === 'file') {
        uploadMethod.classList.add('active');
        cameraMethod.classList.remove('active');
        cameraContainer.classList.remove('active');
        stopCamera();
        
        // Trigger file input click
        console.log('📤 Opening file picker...');
        fileInput.click();
        
    } else if (method === 'camera') {
        cameraMethod.classList.add('active');
        uploadMethod.classList.remove('active');
        cameraContainer.classList.add('active');
        startCamera();
    }
}

// ==================== CAMERA FUNCTIONS ====================

async function startCamera() {
    try {
        // Check if camera API is available
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('CAMERA_NOT_SUPPORTED');
        }

        const constraints = {
            video: {
                facingMode: 'environment', // Use back camera on mobile
                width: { ideal: 1920 },
                height: { ideal: 1080 }
            }
        };

        videoStream = await navigator.mediaDevices.getUserMedia(constraints);
        const video = document.getElementById('video');
        video.srcObject = videoStream;
        
        // Wait for video to be ready
        video.onloadedmetadata = () => {
            // Initialize edge detector
            if (window.EdgeDetector) {
                edgeDetector = new EdgeDetector(video);
                edgeDetector.startDetection(updateGuideBox);
                console.log('✅ Edge detection started');
            } else {
                console.warn('⚠️ Edge detector not loaded, using static guide');
            }
        };
        
        console.log('✅ Camera started successfully');
    } catch (error) {
        console.error('Error accessing camera:', error);
        
        let errorMessage = '';
        
        // Check if it's a mobile device accessing via HTTP (not HTTPS)
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        const isHTTP = window.location.protocol === 'http:';
        const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
        
        if (isMobile && isHTTP && !isLocalhost) {
            errorMessage = '📱 Camera requires HTTPS on mobile devices.\n\n' +
                          '✅ SOLUTION: Use "Upload Image" instead!\n' +
                          '   • Click "Upload Image" above\n' +
                          '   • Take photo with your phone camera\n' +
                          '   • Select the photo to upload\n' +
                          '   • Works perfectly - same results!\n\n' +
                          '🔧 Alternative: Enable HTTPS (advanced users only)\n' +
                          '   See MOBILE_CAMERA.md for instructions';
        } else if (error.message === 'CAMERA_NOT_SUPPORTED') {
            errorMessage = 'Your browser does not support camera access. Please use Chrome or Safari, or use "Upload Image" instead.';
        } else if (error.name === 'NotAllowedError') {
            errorMessage = '📷 Camera permission denied.\n\n' +
                          'To allow camera access:\n' +
                          '1. Click the camera icon in your browser address bar\n' +
                          '2. Select "Allow"\n' +
                          '3. Refresh the page and try again\n\n' +
                          'Or use "Upload Image" - works great!';
        } else if (error.name === 'NotFoundError') {
            errorMessage = 'No camera found on this device. Please use "Upload Image" to select photos instead.';
        } else if (error.name === 'NotReadableError') {
            errorMessage = 'Camera is being used by another application. Please close other apps and try again, or use "Upload Image".';
        } else {
            errorMessage = 'Could not access camera. Please use "Upload Image" instead - it works just as well!';
        }
        
        showError(errorMessage);
        closeCamera();
    }
}

function stopCamera() {
    if (videoStream) {
        videoStream.getTracks().forEach(track => track.stop());
        videoStream = null;
    }
    
    // Stop edge detection
    if (edgeDetector) {
        edgeDetector.stopDetection();
        edgeDetector = null;
    }
}

// Update guide box based on detected edges
function updateGuideBox(corners) {
    const guideBox = document.querySelector('.camera-guide');
    if (!guideBox) return;
    
    if (corners) {
        // Receipt detected! Update guide box
        detectedCorners = corners;
        
        // Calculate position and size in percentage
        const left = corners.topLeft.x * 100;
        const top = corners.topLeft.y * 100;
        const width = corners.width * 100;
        const height = corners.height * 100;
        
        // Animate guide box to detected position
        guideBox.style.left = `${left}%`;
        guideBox.style.top = `${top}%`;
        guideBox.style.width = `${width}%`;
        guideBox.style.height = `${height}%`;
        guideBox.style.transform = 'none'; // Remove centering
        
        // Add "ready" class for visual feedback
        guideBox.classList.add('ready');
        
        // Update instruction
        const instruction = document.querySelector('.camera-instructions');
        if (instruction) {
            instruction.textContent = '✓ Receipt detected! Hold steady and capture';
            instruction.style.background = 'rgba(16, 185, 129, 0.9)';
        }
    } else {
        // No receipt detected, reset to default
        detectedCorners = null;
        
        // Reset guide box to center
        guideBox.style.left = '';
        guideBox.style.top = '';
        guideBox.style.width = '';
        guideBox.style.height = '';
        guideBox.style.transform = 'translate(-50%, -50%)';
        guideBox.classList.remove('ready');
        
        // Reset instruction
        const instruction = document.querySelector('.camera-instructions');
        if (instruction) {
            instruction.textContent = '📄 Align receipt within the frame';
            instruction.style.background = 'rgba(0, 0, 0, 0.7)';
        }
    }
}

function capturePhoto() {
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const context = canvas.getContext('2d');

    // Set canvas to video dimensions
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    // Draw current video frame to canvas
    context.drawImage(video, 0, 0);

    // Convert to image
    canvas.toBlob((blob) => {
        const url = URL.createObjectURL(blob);
        
        // Always close camera before showing adjustment
        closeCamera();
        
        // Show corner adjustment UI (works for both single and multi-image mode)
        showCornerAdjustment(url, blob, detectedCorners, multiImageMode);
        
    }, 'image/jpeg', 0.95);
}

/**
 * Show brief feedback message
 */
function showBriefFeedback(message) {
    const instruction = document.querySelector('.camera-instructions');
    if (instruction) {
        const originalText = instruction.textContent;
        const originalBg = instruction.style.background;
        
        instruction.textContent = `✓ ${message}`;
        instruction.style.background = 'rgba(16, 185, 129, 0.9)';
        
        setTimeout(() => {
            instruction.textContent = originalText;
            instruction.style.background = originalBg;
        }, 2000);
    }
}

/**
 * Show corner adjustment UI after capture
 */
function showCornerAdjustment(imageUrl, imageBlob, corners, isMultiImage = false) {
    console.log('📐 Showing corner adjustment UI (multi-image:', isMultiImage, ')');
    
    // Hide upload section
    document.getElementById('uploadSection') && document.getElementById('uploadSection').classList.remove('active');
    
    // Create adjustment UI
    const adjustmentSection = document.createElement('div');
    adjustmentSection.id = 'adjustmentSection';
    adjustmentSection.className = 'adjustment-section active';
    
    // Different UI based on mode
    if (isMultiImage) {
        // Multi-image mode: show "Add to Collection" button
        adjustmentSection.innerHTML = `
            <h3 style="margin-bottom: 15px; color: var(--dark);">
                Adjust Crop Area - Image ${capturedImages.length + 1}
            </h3>
            <p style="margin-bottom: 20px; color: var(--gray); font-size: 0.9rem;">
                Drag the corners to adjust the crop area. This image will be added to your collection for stitching.
            </p>
            
            <div style="position: relative; margin-bottom: 20px;">
                <img id="adjustmentImage" src="${imageUrl}" style="width: 100%; max-height: 500px; object-fit: contain; border-radius: 10px; display: block;">
            </div>
            
            <div class="action-buttons">
                <button class="btn btn-success" onclick="addToMultiImageCollection()">
                    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                    </svg>
                    Add & Continue
                </button>
                <button class="btn btn-primary" onclick="addToMultiImageCollectionAndProcess()">
                    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                    </svg>
                    Add & Process All
                </button>
                <button class="btn btn-secondary" onclick="retakePhoto()">
                    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"></path>
                    </svg>
                    Retake
                </button>
                <button class="btn btn-secondary" onclick="cancelMultiImageAdjustment()">
                    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                    Cancel
                </button>
            </div>
        `;
    } else {
        // Single image mode: original buttons
        adjustmentSection.innerHTML = `
            <h3 style="margin-bottom: 15px; color: var(--dark);">Adjust Crop Area</h3>
            <p style="margin-bottom: 20px; color: var(--gray); font-size: 0.9rem;">
                Drag the corners to adjust the crop area. The green box shows what will be processed.
            </p>
            
            <div style="position: relative; margin-bottom: 20px;">
                <img id="adjustmentImage" src="${imageUrl}" style="width: 100%; max-height: 500px; object-fit: contain; border-radius: 10px; display: block;">
            </div>
            
            <div class="action-buttons">
                <button class="btn btn-primary" onclick="applyAdjustment()">
                    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                    </svg>
                    Apply & Process
                </button>
                <button class="btn btn-secondary" onclick="cancelAdjustment()">
                    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                    Cancel
                </button>
                <button class="btn btn-secondary" onclick="retakePhoto()">
                    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"></path>
                    </svg>
                    Retake
                </button>
            </div>
        `;
    }
    
    // Add to page
    const mainCard = document.querySelector('.main-card');
    mainCard.appendChild(adjustmentSection);
    
    // Wait for image to load, then init corner adjuster
    const img = document.getElementById('adjustmentImage');
    img.onload = () => {
        // Use detected corners if available, otherwise defaults
        const initialCorners = corners || null;
        
        window.cornerAdjuster = new CornerAdjuster(img, initialCorners);
        
        // Store the blob and URL for later processing
        window.capturedImageBlob = imageBlob;
        window.capturedImageUrl = imageUrl;
        
        console.log('✅ Corner adjustment ready');
    };
}

/**
 * Apply corner adjustment and process
 */
function applyAdjustment() {
    if (!window.cornerAdjuster || !window.capturedImageBlob) {
        console.error('❌ No adjustment data available');
        return;
    }
    
    const adjustedCorners = window.cornerAdjuster.getCorners();
    console.log('📐 Applying adjusted corners:', adjustedCorners);
    
    // Convert blob to image for cropping
    const img = new Image();
    const blobUrl = URL.createObjectURL(window.capturedImageBlob);
    
    img.onload = () => {
        console.log('🖼️ Image loaded:', img.width, 'x', img.height);
        
        // Create canvas with original image
        const sourceCanvas = document.createElement('canvas');
        const sourceCtx = sourceCanvas.getContext('2d');
        sourceCanvas.width = img.width;
        sourceCanvas.height = img.height;
        sourceCtx.drawImage(img, 0, 0);
        
        // Apply crop with adjusted corners (using pixel coordinates)
        const croppedCanvas = cropToCorners(sourceCanvas, adjustedCorners);
        
        console.log('✅ Cropped to:', croppedCanvas.width, 'x', croppedCanvas.height);
        
        // Convert to blob
        croppedCanvas.toBlob((blob) => {
            const file = new File([blob], 'receipt-adjusted.jpg', { type: 'image/jpeg' });
            
            // Clean up
            URL.revokeObjectURL(blobUrl);
            cancelAdjustment();
            
            // Show preview and allow processing
            handleFileSelect({ target: { files: [file] } });
            
        }, 'image/jpeg', 0.95);
    };
    
    img.onerror = () => {
        console.error('❌ Failed to load image');
        showError('Failed to process image. Please try again.');
        URL.revokeObjectURL(blobUrl);
    };
    
    img.src = blobUrl;
}

/**
 * Crop image to specified corners with perspective correction
 * This ensures EXACTLY what's in the green box is cropped, nothing more, nothing less
 */
function cropToCorners(sourceCanvas, corners) {
    const width = sourceCanvas.width;
    const height = sourceCanvas.height;
    
    console.log('🔍 cropToCorners called:');
    console.log('   Source:', width, 'x', height);
    console.log('   Corners:', corners);
    
    // Validate input
    if (!corners || !corners.topLeft || !corners.topRight || !corners.bottomLeft || !corners.bottomRight) {
        console.error('❌ Invalid corners, returning original');
        return sourceCanvas;
    }
    
    // Convert normalized coordinates to pixel coordinates with strict bounds
    const pixelCorners = {
        topLeft: { 
            x: Math.max(0, Math.min(1, corners.topLeft.x)) * width, 
            y: Math.max(0, Math.min(1, corners.topLeft.y)) * height 
        },
        topRight: { 
            x: Math.max(0, Math.min(1, corners.topRight.x)) * width, 
            y: Math.max(0, Math.min(1, corners.topRight.y)) * height 
        },
        bottomLeft: { 
            x: Math.max(0, Math.min(1, corners.bottomLeft.x)) * width, 
            y: Math.max(0, Math.min(1, corners.bottomLeft.y)) * height 
        },
        bottomRight: { 
            x: Math.max(0, Math.min(1, corners.bottomRight.x)) * width, 
            y: Math.max(0, Math.min(1, corners.bottomRight.y)) * height 
        }
    };
    
    console.log('📍 Pixel corners:', pixelCorners);
    
    // Calculate bounding box (simple rectangle crop - more reliable than perspective)
    const minX = Math.floor(Math.min(
        pixelCorners.topLeft.x,
        pixelCorners.topRight.x,
        pixelCorners.bottomLeft.x,
        pixelCorners.bottomRight.x
    ));
    const maxX = Math.ceil(Math.max(
        pixelCorners.topLeft.x,
        pixelCorners.topRight.x,
        pixelCorners.bottomLeft.x,
        pixelCorners.bottomRight.x
    ));
    const minY = Math.floor(Math.min(
        pixelCorners.topLeft.y,
        pixelCorners.topRight.y,
        pixelCorners.bottomLeft.y,
        pixelCorners.bottomRight.y
    ));
    const maxY = Math.ceil(Math.max(
        pixelCorners.topLeft.y,
        pixelCorners.topRight.y,
        pixelCorners.bottomLeft.y,
        pixelCorners.bottomRight.y
    ));
    
    // Calculate dimensions
    let cropWidth = maxX - minX;
    let cropHeight = maxY - minY;
    
    console.log('📏 Initial crop:', cropWidth, 'x', cropHeight, 'at', minX, ',', minY);
    
    // Validate dimensions
    if (cropWidth <= 0 || cropHeight <= 0) {
        console.error('❌ Invalid dimensions:', cropWidth, 'x', cropHeight);
        console.error('   Returning original image');
        return sourceCanvas;
    }
    
    // Ensure minimum size
    if (cropWidth < 50 || cropHeight < 50) {
        console.warn('⚠️ Crop too small, using minimum 50x50');
        cropWidth = Math.max(cropWidth, 50);
        cropHeight = Math.max(cropHeight, 50);
    }
    
    // Ensure we don't exceed canvas bounds
    const safeX = Math.max(0, Math.min(minX, width - 1));
    const safeY = Math.max(0, Math.min(minY, height - 1));
    const safeWidth = Math.min(cropWidth, width - safeX);
    const safeHeight = Math.min(cropHeight, height - safeY);
    
    console.log('✅ Safe crop:', safeWidth, 'x', safeHeight, 'at', safeX, ',', safeY);
    
    // Final validation
    if (safeWidth <= 0 || safeHeight <= 0) {
        console.error('❌ Safe dimensions invalid:', safeWidth, 'x', safeHeight);
        return sourceCanvas;
    }
    
    try {
        // Create output canvas
        const outputCanvas = document.createElement('canvas');
        outputCanvas.width = Math.max(1, Math.floor(safeWidth));
        outputCanvas.height = Math.max(1, Math.floor(safeHeight));
        const outputCtx = outputCanvas.getContext('2d');
        
        if (!outputCtx) {
            console.error('❌ Failed to get canvas context');
            return sourceCanvas;
        }
        
        // Fill with white background first (prevents black images)
        outputCtx.fillStyle = '#FFFFFF';
        outputCtx.fillRect(0, 0, outputCanvas.width, outputCanvas.height);
        
        // Draw the cropped region
        outputCtx.drawImage(
            sourceCanvas,
            safeX, safeY, safeWidth, safeHeight,     // Source rectangle
            0, 0, outputCanvas.width, outputCanvas.height  // Destination rectangle
        );
        
        // Verify we got content (check a few pixels)
        const testData = outputCtx.getImageData(
            Math.floor(outputCanvas.width / 2),
            Math.floor(outputCanvas.height / 2),
            1, 1
        );
        
        const isBlank = testData.data[0] === 255 && 
                       testData.data[1] === 255 && 
                       testData.data[2] === 255;
        
        if (isBlank) {
            console.warn('⚠️ Center pixel is white, image may be blank');
        }
        
        console.log('✅ Crop successful:', outputCanvas.width, 'x', outputCanvas.height);
        
        // Apply image enhancement
        enhanceImageForOCR(outputCtx, outputCanvas.width, outputCanvas.height);
        
        return outputCanvas;
        
    } catch (error) {
        console.error('❌ Error during crop:', error);
        console.error('   Stack:', error.stack);
        return sourceCanvas;
    }
}

/**
 * Cancel adjustment and go back
 */
function cancelAdjustment() {
    const adjustmentSection = document.getElementById('adjustmentSection');
    if (adjustmentSection) {
        if (window.cornerAdjuster) {
            window.cornerAdjuster.destroy();
            window.cornerAdjuster = null;
        }
        adjustmentSection.remove();
    }
    
    window.capturedImageBlob = null;
}

/**
 * Retake photo
 */
function retakePhoto() {
    cancelAdjustment();
    selectUploadMethod('camera');
}

/**
 * Add adjusted image to multi-image collection and continue
 */
function addToMultiImageCollection() {
    if (!window.cornerAdjuster || !window.capturedImageBlob) {
        console.error('❌ No adjustment data available');
        return;
    }
    
    const adjustedCorners = window.cornerAdjuster.getCorners();
    console.log('📐 Adding image to collection with adjusted corners');
    
    // Crop the image with adjusted corners
    cropAndAddToCollection(adjustedCorners, false);
}

/**
 * Add adjusted image to collection and process all immediately
 */
function addToMultiImageCollectionAndProcess() {
    if (!window.cornerAdjuster || !window.capturedImageBlob) {
        console.error('❌ No adjustment data available');
        return;
    }
    
    const adjustedCorners = window.cornerAdjuster.getCorners();
    console.log('📐 Adding final image and processing all');
    
    // Crop the image with adjusted corners
    cropAndAddToCollection(adjustedCorners, true);
}

/**
 * Crop image and add to multi-image collection
 */
function cropAndAddToCollection(corners, processAfter = false) {
    console.log('🔄 cropAndAddToCollection called');
    console.log('   Process after:', processAfter);
    console.log('   Corners:', corners);
    
    if (!window.capturedImageBlob) {
        console.error('❌ No captured image blob available');
        showError('No image to process. Please capture again.');
        return;
    }
    
    const img = new Image();
    const blobUrl = URL.createObjectURL(window.capturedImageBlob);
    
    img.onload = () => {
        console.log('🖼️ Image loaded:', img.width, 'x', img.height);
        
        // Create canvas with original image
        const sourceCanvas = document.createElement('canvas');
        const sourceCtx = sourceCanvas.getContext('2d');
        sourceCanvas.width = img.width;
        sourceCanvas.height = img.height;
        
        // Fill with white background first
        sourceCtx.fillStyle = '#FFFFFF';
        sourceCtx.fillRect(0, 0, sourceCanvas.width, sourceCanvas.height);
        
        // Draw original image
        sourceCtx.drawImage(img, 0, 0);
        
        console.log('📋 Source canvas created:', sourceCanvas.width, 'x', sourceCanvas.height);
        
        // Apply crop with adjusted corners
        const croppedCanvas = cropToCorners(sourceCanvas, corners);
        
        if (!croppedCanvas || croppedCanvas.width === 0 || croppedCanvas.height === 0) {
            console.error('❌ Crop failed, invalid canvas');
            showError('Failed to crop image. Please try adjusting corners again.');
            URL.revokeObjectURL(blobUrl);
            return;
        }
        
        console.log('✅ Cropped to:', croppedCanvas.width, 'x', croppedCanvas.height);
        
        // Convert to blob
        croppedCanvas.toBlob((blob) => {
            if (!blob || blob.size === 0) {
                console.error('❌ Generated blob is invalid');
                showError('Failed to create image. Please try again.');
                URL.revokeObjectURL(blobUrl);
                return;
            }
            
            console.log('💾 Blob created:', blob.size, 'bytes');
            
            const croppedUrl = URL.createObjectURL(blob);
            
            // Add to collection
            capturedImages.push({
                blob: blob,
                url: croppedUrl,
                corners: corners
            });
            
            currentImageIndex++;
            
            console.log(`✅ Image ${currentImageIndex} added to collection`);
            
            // Clean up
            URL.revokeObjectURL(blobUrl);
            cancelAdjustment();
            
            // Update status
            updateMultiImageStatus();
            
            if (processAfter && capturedImages.length >= 2) {
                // Process immediately
                console.log('🔗 Processing all images now');
                processMultipleImages();
            } else {
                // Continue capturing - reopen camera
                console.log('📸 Reopening camera for next capture');
                selectUploadMethod('camera');
            }
            
        }, 'image/jpeg', 0.95);
    };
    
    img.onerror = (error) => {
        console.error('❌ Failed to load image:', error);
        showError('Failed to process image. Please try again.');
        URL.revokeObjectURL(blobUrl);
    };
    
    img.src = blobUrl;
}

/**
 * Cancel multi-image adjustment and go back
 */
function cancelMultiImageAdjustment() {
    // Clean up
    if (window.capturedImageUrl) {
        URL.revokeObjectURL(window.capturedImageUrl);
    }
    
    cancelAdjustment();
    
    // Show upload section again with status
    const uploadSection = document.getElementById('uploadSection');
    if (uploadSection) {
        uploadSection.style.display = 'block';
    }
    
    updateMultiImageStatus();
}

function applyDetectedCrop(sourceCanvas, corners) {
    const ctx = sourceCanvas.getContext('2d');
    const width = sourceCanvas.width;
    const height = sourceCanvas.height;
    
    // Convert normalized coordinates to pixels
    const x = corners.topLeft.x * width;
    const y = corners.topLeft.y * height;
    const cropWidth = corners.width * width;
    const cropHeight = corners.height * height;
    
    console.log(`📐 Auto-detected crop:`);
    console.log(`   Source: ${width}x${height}`);
    console.log(`   Position: (${Math.round(x)}, ${Math.round(y)})`);
    console.log(`   Size: ${Math.round(cropWidth)}x${Math.round(cropHeight)}`);
    
    // Ensure we're within bounds
    const safeX = Math.max(0, Math.min(x, width - 1));
    const safeY = Math.max(0, Math.min(y, height - 1));
    const safeWidth = Math.max(1, Math.min(cropWidth, width - safeX));
    const safeHeight = Math.max(1, Math.min(cropHeight, height - safeY));
    
    // Create a new canvas for the cropped image
    const croppedCanvas = document.createElement('canvas');
    croppedCanvas.width = safeWidth;
    croppedCanvas.height = safeHeight;
    const croppedCtx = croppedCanvas.getContext('2d');
    
    // Extract the detected region
    croppedCtx.drawImage(
        sourceCanvas,
        safeX, safeY, safeWidth, safeHeight,  // Source rectangle
        0, 0, safeWidth, safeHeight            // Destination rectangle
    );
    
    console.log(`✅ Cropped result: ${croppedCanvas.width}x${croppedCanvas.height}`);
    
    // Apply image enhancement for better OCR
    enhanceImageForOCR(croppedCtx, safeWidth, safeHeight);
    
    return croppedCanvas;
}

function applySmartCrop(sourceCanvas) {
    const ctx = sourceCanvas.getContext('2d');
    const width = sourceCanvas.width;
    const height = sourceCanvas.height;
    
    // Calculate guide rectangle bounds (80% of frame, centered, 3:4 aspect ratio)
    const guideWidth = width * 0.8;
    const guideHeight = guideWidth * (4/3); // 3:4 aspect ratio
    
    // Center the guide
    const guideX = (width - guideWidth) / 2;
    const guideY = (height - guideHeight) / 2;
    
    // Create a new canvas for the cropped image
    const croppedCanvas = document.createElement('canvas');
    croppedCanvas.width = guideWidth;
    croppedCanvas.height = guideHeight;
    const croppedCtx = croppedCanvas.getContext('2d');
    
    // Extract the region within the guide
    croppedCtx.drawImage(
        sourceCanvas,
        guideX, guideY, guideWidth, guideHeight,  // Source rectangle
        0, 0, guideWidth, guideHeight              // Destination rectangle
    );
    
    console.log(`📐 Cropped to guide area: ${Math.round(guideWidth)}x${Math.round(guideHeight)}`);
    
    // Apply image enhancement for better OCR
    enhanceImageForOCR(croppedCtx, guideWidth, guideHeight);
    
    return croppedCanvas;
}

function enhanceImageForOCR(ctx, width, height) {
    // Get image data
    const imageData = ctx.getImageData(0, 0, width, height);
    const data = imageData.data;
    
    // Apply contrast enhancement
    const factor = 1.2; // Increase contrast by 20%
    const intercept = 128 * (1 - factor);
    
    for (let i = 0; i < data.length; i += 4) {
        // Apply contrast to RGB channels
        data[i] = Math.min(255, Math.max(0, data[i] * factor + intercept));     // Red
        data[i + 1] = Math.min(255, Math.max(0, data[i + 1] * factor + intercept)); // Green
        data[i + 2] = Math.min(255, Math.max(0, data[i + 2] * factor + intercept)); // Blue
        // Alpha channel (i + 3) remains unchanged
    }
    
    // Put enhanced image data back
    ctx.putImageData(imageData, 0, 0);
    
    console.log('✨ Applied image enhancement for better OCR');
}

function closeCamera() {
    stopCamera();
    document.getElementById('cameraContainer').classList.remove('active');
    document.getElementById('cameraMethod').classList.remove('active');
}

// ==================== FILE HANDLING ====================

function handleFileSelect(event) {
    console.log('📁 File selection event triggered');
    
    const file = event.target.files[0];
    
    if (!file) {
        console.log('❌ No file selected');
        return;
    }
    
    console.log('✅ File selected:', file.name, 'Type:', file.type, 'Size:', file.size);

    // Validate file type
    const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];
    if (!validTypes.includes(file.type)) {
        console.error('❌ Invalid file type:', file.type);
        showError('Invalid file type. Please upload JPG, PNG, or PDF files.');
        return;
    }

    // Validate file size (10MB max)
    const maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) {
        console.error('❌ File too large:', file.size);
        showError('File too large. Maximum size is 10MB.');
        return;
    }

    currentFile = file;
    console.log('✅ File validated, showing preview...');
    showPreview(file);
}

function showPreview(file) {
    console.log('🖼️ Generating preview for:', file.name);
    
    const reader = new FileReader();
    
    reader.onload = (e) => {
        console.log('✅ File read successfully');
        const previewImage = document.getElementById('previewImage');
        previewImage.src = e.target.result;
        previewImage.style.maxWidth = '100%';
        previewImage.style.height = 'auto';
        previewImage.style.display = 'block';
        document.getElementById('previewSection').classList.add('active');
        hideError();
        console.log('✅ Preview displayed');
    };
    
    reader.onerror = (e) => {
        console.error('❌ Error reading file:', e);
        showError('Error reading file. Please try again.');
    };
    
    reader.readAsDataURL(file);
}

/**
 * Process multiple images with stitching
 */
async function processMultipleImages() {
    if (capturedImages.length < 2) {
        showError('Please capture at least 2 images to stitch');
        return;
    }
    
    console.log(`🔗 Processing ${capturedImages.length} images with stitching`);
    
    // Show processing indicator
    document.getElementById('processingIndicator').classList.add('active');
    document.getElementById('multiImageStatus').classList.remove('active');
    hideError();
    
    try {
        // Create FormData with all images
        const formData = new FormData();
        
        capturedImages.forEach((img, index) => {
            formData.append('files', img.blob, `receipt-part-${index + 1}.jpg`);
        });
        
        // Enable stitching
        formData.append('stitch', 'true');
        
        console.log('📤 Sending multiple images to API for stitching...');
        
        const response = await fetch(`${API_BASE_URL}/api/v1/ocr/scan-multiple`, {
            method: 'POST',
            body: formData
        });
        
        console.log('📥 Response status:', response.status);
        
        if (!response.ok) {
            const error = await response.json();
            console.error('❌ API Error:', error);
            throw new Error(error.detail || 'Stitching failed');
        }
        
        const results = await response.json();
        console.log('✅ Stitching results received:', results);
        
        // Clear captured images
        clearCapturedImages();
        
        // Display results
        currentResults = results;
        displayResults(results);
        
        // Show stitching info
        if (results.stitching_method) {
            showStitchingInfo(results.stitching_method, capturedImages.length);
        }
        
    } catch (error) {
        console.error('💥 Error processing multiple images:', error);
        showError(`Stitching failed: ${error.message}`);
        document.getElementById('processingIndicator').classList.remove('active');
        document.getElementById('multiImageStatus').classList.add('active');
    }
}

/**
 * Show stitching information
 */
function showStitchingInfo(method, imageCount) {
    const statsGrid = document.getElementById('statsGrid');
    
    // Add stitching info card
    const stitchCard = document.createElement('div');
    stitchCard.className = 'stat-card';
    stitchCard.style.gridColumn = 'span 2';
    stitchCard.style.background = 'linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)';
    stitchCard.style.color = 'white';
    stitchCard.innerHTML = `
        <h4 style="color: white; opacity: 0.9;">Stitching Info</h4>
        <div class="value" style="color: white; font-size: 1.2rem;">
            ${imageCount} images combined
        </div>
        <p style="margin-top: 5px; font-size: 0.85rem; opacity: 0.9;">
            Method: ${method}
        </p>
    `;
    
    statsGrid.insertBefore(stitchCard, statsGrid.firstChild);
}

// ==================== OCR PROCESSING ====================

async function processReceipt() {
    if (!currentFile) {
        showError('No file selected');
        return;
    }

    // Show processing indicator
    document.getElementById('processingIndicator').classList.add('active');
    document.getElementById('previewSection').classList.remove('active');
    hideError();

    try {
        const formData = new FormData();
        formData.append('file', currentFile);

        console.log('📤 Sending request to API...');
        console.log('File:', currentFile.name, 'Size:', currentFile.size);

        const response = await fetch(`${API_BASE_URL}/api/v1/ocr/scan-with-metadata`, {
            method: 'POST',
            body: formData
        });

        console.log('📥 Response status:', response.status);

        if (!response.ok) {
            const error = await response.json();
            console.error('❌ API Error:', error);
            throw new Error(error.detail || 'Processing failed');
        }

        const results = await response.json();
        console.log('✅ Results received:', results);
        
        // Debug: Log what we got
        console.log('Lines:', results.lines?.length || 0);
        console.log('Formatted text:', results.formatted_text?.substring(0, 100));
        console.log('Metadata:', results.metadata);
        
        currentResults = results;
        displayResults(results);

    } catch (error) {
        console.error('💥 Error processing receipt:', error);
        showError(`Processing failed: ${error.message}`);
        document.getElementById('processingIndicator').classList.remove('active');
        document.getElementById('previewSection').classList.add('active');
    }
}

// ==================== RESULTS DISPLAY ====================

function displayResults(results) {
    console.log('🎨 Displaying results...');
    
    // Hide processing, show results
    document.getElementById('processingIndicator').classList.remove('active');
    document.getElementById('resultsSection').classList.add('active');

    // Display statistics
    displayStatistics(results);

    // Display formatted text (prioritize formatted_text if available)
    const formattedText = results.formatted_text || results.text || '';
    console.log('Formatted text length:', formattedText.length);
    document.getElementById('formattedText').textContent = formattedText;

    // Display raw text
    const rawText = results.text || '';
    console.log('Raw text length:', rawText.length);
    document.getElementById('rawText').textContent = rawText;

    // Display metadata
    displayMetadata(results);

    // Display all lines
    const lines = results.lines || [];
    console.log('Displaying', lines.length, 'lines');
    displayLines(lines);
    
    console.log('✅ Results displayed successfully');
}

function displayStatistics(results) {
    const statsGrid = document.getElementById('statsGrid');
    
    const confidence = Math.round((results.confidence || 0) * 100);
    const linesDetected = results.lines_detected || 0;
    const rowsDetected = results.rows_detected || 0;
    const processingTime = results.processing_time_ms || 0;

    statsGrid.innerHTML = `
        <div class="stat-card success">
            <h4>Confidence</h4>
            <div class="value">${confidence}%</div>
        </div>
        <div class="stat-card">
            <h4>Lines Detected</h4>
            <div class="value">${linesDetected}</div>
        </div>
        ${rowsDetected ? `
        <div class="stat-card">
            <h4>Rows Detected</h4>
            <div class="value">${rowsDetected}</div>
        </div>
        ` : ''}
        <div class="stat-card">
            <h4>Processing Time</h4>
            <div class="value">${(processingTime / 1000).toFixed(2)}s</div>
        </div>
    `;
}

function displayMetadata(results) {
    const metadataGrid = document.getElementById('metadataGrid');
    
    // Handle both old and new metadata structures
    const metadata = results.metadata || {};
    const merchant = metadata.merchant_name || results.merchant_name || 'Not detected';
    const total = metadata.total_amount || results.total || 'Not detected';
    const date = metadata.date || results.date || 'Not detected';
    const items = metadata.estimated_items || results.items_count || 'N/A';

    console.log('Metadata:', { merchant, total, date, items });

    metadataGrid.innerHTML = `
        <div class="metadata-item">
            <label>Merchant</label>
            <span class="value">${merchant}</span>
        </div>
        <div class="metadata-item">
            <label>Total Amount</label>
            <span class="value">${total}</span>
        </div>
        <div class="metadata-item">
            <label>Date</label>
            <span class="value">${date}</span>
        </div>
        <div class="metadata-item">
            <label>Estimated Items</label>
            <span class="value">${items}</span>
        </div>
    `;
}

function displayLines(lines) {
    const linesList = document.getElementById('linesList');
    
    console.log('📝 Displaying lines. Count:', lines?.length || 0);
    
    if (!lines || lines.length === 0) {
        console.warn('⚠️ No lines to display');
        linesList.innerHTML = '<p style="text-align: center; color: var(--gray); padding: 20px;">No lines detected</p>';
        return;
    }

    linesList.innerHTML = lines.map((line, index) => {
        const confidence = Math.round((line.confidence || 0) * 100);
        const badgeClass = confidence >= 90 ? 'confidence-high' : 
                          confidence >= 70 ? 'confidence-medium' : 'confidence-low';
        
        return `
            <div class="line-item">
                <span class="line-text">${line.text || ''}</span>
                <span class="confidence-badge ${badgeClass}">${confidence}%</span>
            </div>
        `;
    }).join('');
    
    console.log('✅ Lines displayed successfully');
}

// ==================== TAB SWITCHING ====================

function switchTab(tabName) {
    currentTab = tabName;

    // Update tab buttons
    document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    // Show selected tab
    const tabButton = event.target;
    const tabContent = document.getElementById(`${tabName}Tab`);
    
    tabButton.classList.add('active');
    tabContent.classList.add('active');
}

// ==================== ACTIONS ====================

function copyToClipboard() {
    let textToCopy = '';
    
    switch(currentTab) {
        case 'formatted':
            textToCopy = document.getElementById('formattedText').textContent;
            break;
        case 'raw':
            textToCopy = document.getElementById('rawText').textContent;
            break;
        default:
            textToCopy = document.getElementById('formattedText').textContent;
    }

    navigator.clipboard.writeText(textToCopy).then(() => {
        // Show success feedback
        const btn = event.target.closest('.btn');
        const originalText = btn.innerHTML;
        btn.innerHTML = `
            <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
            </svg>
            Copied!
        `;
        btn.style.background = 'var(--success)';
        
        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.style.background = '';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
        showError('Failed to copy to clipboard');
    });
}

function downloadJSON() {
    if (!currentResults) return;

    const dataStr = JSON.stringify(currentResults, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = `receipt-ocr-${Date.now()}.json`;
    link.click();
    
    URL.revokeObjectURL(url);
}

function reset() {
    // Reset state
    currentFile = null;
    currentResults = null;
    currentTab = 'formatted';
    
    // Clear multi-image state
    if (capturedImages.length > 0) {
        clearCapturedImages();
    }

    // Reset UI
    document.getElementById('previewSection').classList.remove('active');
    document.getElementById('resultsSection').classList.remove('active');
    document.getElementById('processingIndicator').classList.remove('active');
    document.getElementById('uploadMethod').classList.remove('active');
    document.getElementById('cameraMethod').classList.remove('active');
    document.getElementById('fileInput').value = '';
    
    // Show upload section again
    const uploadSection = document.getElementById('uploadSection');
    if (uploadSection) {
        uploadSection.style.display = 'block';
    }
    
    // Reset tabs
    document.querySelectorAll('.tab').forEach((tab, index) => {
        tab.classList.toggle('active', index === 0);
    });
    document.querySelectorAll('.tab-content').forEach((content, index) => {
        content.classList.toggle('active', index === 0);
    });

    hideError();
    stopCamera();
    
    // Restore multi-image status if in multi-image mode
    if (multiImageMode) {
        updateMultiImageStatus();
    }
}

// ==================== ERROR HANDLING ====================

function showError(message) {
    const errorElement = document.getElementById('errorMessage');
    errorElement.textContent = message;
    errorElement.classList.add('active');
}

function hideError() {
    document.getElementById('errorMessage').classList.remove('active');
}

// ==================== INITIALIZATION ====================

// Check API health on load
async function checkAPIHealth() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (!response.ok) throw new Error('API not responding');
        console.log('✅ API is healthy');
    } catch (error) {
        console.warn('⚠️ API not available:', error);
        showError('API server is not running. Please start the server with: python main.py');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    checkAPIHealth();
    
    // Show mobile notice if on mobile HTTP (not HTTPS)
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    const isHTTP = window.location.protocol === 'http:';
    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    
    if (isMobile && isHTTP && !isLocalhost) {
        const notice = document.getElementById('mobileNotice');
        if (notice) {
            notice.style.display = 'block';
        }
        console.log('📱 Mobile device on HTTP detected - showing upload recommendation');
    }
    
    console.log('📱 App initialized');
    console.log('Camera API available:', !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia));
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopCamera();
});