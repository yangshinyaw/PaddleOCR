/**
 * Edge Detection Module for Receipt Scanning
 * Real-time document edge detection using Canvas API
 * Similar to CamScanner's auto-detection feature
 * Mobile-optimized version
 */

class EdgeDetector {
    constructor(videoElement) {
        this.video = videoElement;
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d', { willReadFrequently: true });
        this.isDetecting = false;
        this.detectedCorners = null;
        this.frameCount = 0;
        this.isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        
        // Mobile optimization: lower resolution for faster processing
        this.processingScale = this.isMobile ? 0.25 : 0.5;
    }

    /**
     * Start real-time edge detection
     */
    startDetection(callback) {
        this.isDetecting = true;
        this.detectLoop(callback);
        console.log(`🔍 Edge detection started (mobile: ${this.isMobile}, scale: ${this.processingScale})`);
    }

    /**
     * Stop edge detection
     */
    stopDetection() {
        this.isDetecting = false;
        console.log('⏹️ Edge detection stopped');
    }

    /**
     * Main detection loop
     */
    detectLoop(callback) {
        if (!this.isDetecting) return;

        this.frameCount++;
        
        // Skip frames on mobile for better performance (process every 3rd frame)
        if (this.isMobile && this.frameCount % 3 !== 0) {
            setTimeout(() => this.detectLoop(callback), 33); // ~30 FPS check
            return;
        }

        const corners = this.detectDocumentEdges();
        
        if (corners) {
            this.detectedCorners = corners;
            callback(corners);
        } else {
            callback(null);
        }

        // Mobile: 150ms between detections, Desktop: 100ms
        const interval = this.isMobile ? 150 : 100;
        setTimeout(() => this.detectLoop(callback), interval);
    }

    /**
     * Detect document edges in current video frame
     */
    detectDocumentEdges() {
        const videoWidth = this.video.videoWidth;
        const videoHeight = this.video.videoHeight;

        if (videoWidth === 0 || videoHeight === 0) {
            return null;
        }

        // Process at reduced resolution for speed
        const processWidth = Math.floor(videoWidth * this.processingScale);
        const processHeight = Math.floor(videoHeight * this.processingScale);

        this.canvas.width = processWidth;
        this.canvas.height = processHeight;

        // Draw current video frame at reduced size
        this.ctx.drawImage(this.video, 0, 0, processWidth, processHeight);

        // Get image data
        const imageData = this.ctx.getImageData(0, 0, processWidth, processHeight);

        // Apply edge detection
        const edges = this.detectEdges(imageData);

        // Find the document rectangle
        const receiptRect = this.findDocumentRectangle(edges, processWidth, processHeight);

        return receiptRect;
    }

    /**
     * Fast edge detection optimized for mobile
     */
    detectEdges(imageData) {
        const data = imageData.data;
        const width = imageData.width;
        const height = imageData.height;
        
        // Convert to grayscale first
        const gray = new Uint8ClampedArray(width * height);
        for (let i = 0; i < data.length; i += 4) {
            gray[i / 4] = (data[i] + data[i + 1] + data[i + 2]) / 3;
        }

        // Fast Sobel edge detection
        const edges = new Uint8ClampedArray(width * height);
        
        for (let y = 1; y < height - 1; y++) {
            for (let x = 1; x < width - 1; x++) {
                const idx = y * width + x;
                
                // Sobel kernels
                const gx = 
                    -gray[(y-1)*width + (x-1)] - 2*gray[y*width + (x-1)] - gray[(y+1)*width + (x-1)] +
                     gray[(y-1)*width + (x+1)] + 2*gray[y*width + (x+1)] + gray[(y+1)*width + (x+1)];
                
                const gy = 
                    -gray[(y-1)*width + (x-1)] - 2*gray[(y-1)*width + x] - gray[(y-1)*width + (x+1)] +
                     gray[(y+1)*width + (x-1)] + 2*gray[(y+1)*width + x] + gray[(y+1)*width + (x+1)];
                
                const magnitude = Math.abs(gx) + Math.abs(gy); // Faster than sqrt
                edges[idx] = magnitude > 40 ? 255 : 0; // Lower threshold for better detection
            }
        }

        return { data: edges, width, height };
    }

    /**
     * Find document rectangle using edge density
     */
    findDocumentRectangle(edges, width, height) {
        const data = edges.data;
        
        // Divide image into grid and find density
        const gridSize = 20;
        const cellWidth = Math.floor(width / gridSize);
        const cellHeight = Math.floor(height / gridSize);
        
        const density = new Array(gridSize * gridSize).fill(0);
        
        // Calculate edge density in each cell
        for (let gy = 0; gy < gridSize; gy++) {
            for (let gx = 0; gx < gridSize; gx++) {
                let edgeCount = 0;
                const startX = gx * cellWidth;
                const startY = gy * cellHeight;
                
                for (let y = startY; y < startY + cellHeight && y < height; y++) {
                    for (let x = startX; x < startX + cellWidth && x < width; x++) {
                        if (data[y * width + x] > 128) edgeCount++;
                    }
                }
                
                density[gy * gridSize + gx] = edgeCount;
            }
        }
        
        // Find region with highest edge density (likely the document)
        let maxDensity = 0;
        let bestRegion = { minX: 0, minY: 0, maxX: gridSize - 1, maxY: gridSize - 1 };
        
        // Try different region sizes
        for (let size = Math.floor(gridSize * 0.4); size < gridSize; size++) {
            for (let y = 0; y <= gridSize - size; y++) {
                for (let x = 0; x <= gridSize - size; x++) {
                    let totalDensity = 0;
                    
                    // Sum density in this region
                    for (let dy = 0; dy < size; dy++) {
                        for (let dx = 0; dx < size; dx++) {
                            totalDensity += density[(y + dy) * gridSize + (x + dx)];
                        }
                    }
                    
                    if (totalDensity > maxDensity) {
                        maxDensity = totalDensity;
                        bestRegion = {
                            minX: x,
                            minY: y,
                            maxX: x + size,
                            maxY: y + size
                        };
                    }
                }
            }
        }
        
        // Convert to normalized coordinates
        const x1 = bestRegion.minX / gridSize;
        const y1 = bestRegion.minY / gridSize;
        const x2 = bestRegion.maxX / gridSize;
        const y2 = bestRegion.maxY / gridSize;
        
        const rectWidth = x2 - x1;
        const rectHeight = y2 - y1;
        
        // Validate size
        if (rectWidth < 0.15 || rectHeight < 0.15) return null; // Too small
        if (rectWidth > 0.98 || rectHeight > 0.98) return null; // Too large
        
        // Validate aspect ratio (receipts can be portrait or landscape)
        const aspectRatio = rectHeight / rectWidth;
        if (aspectRatio < 0.3 || aspectRatio > 5) return null;
        
        // Return corners in normalized coordinates (0-1)
        return {
            topLeft: { x: x1, y: y1 },
            topRight: { x: x2, y: y1 },
            bottomLeft: { x: x1, y: y2 },
            bottomRight: { x: x2, y: y2 },
            width: rectWidth,
            height: rectHeight,
            confidence: maxDensity / (bestRegion.maxX - bestRegion.minX) / (bestRegion.maxY - bestRegion.minY)
        };
    }

    /**
     * Get detected corners for cropping
     */
    getDetectedCorners() {
        return this.detectedCorners;
    }
}

// Export for use in main app
window.EdgeDetector = EdgeDetector;