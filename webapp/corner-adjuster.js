/**
 * Corner Adjustment Module
 * Allow users to manually adjust detected corners after capture
 * CamScanner-style corner dragging interface
 */

class CornerAdjuster {
    constructor(imageElement, initialCorners) {
        this.image = imageElement;
        this.corners = initialCorners || this.getDefaultCorners();
        this.selectedCorner = null;
        this.isDragging = false;
        this.overlay = null;
        this.onUpdate = null;
        
        this.createOverlay();
        this.attachEvents();
    }

    /**
     * Get default corners (full image)
     */
    getDefaultCorners() {
        return {
            topLeft: { x: 0.05, y: 0.05 },
            topRight: { x: 0.95, y: 0.05 },
            bottomLeft: { x: 0.05, y: 0.95 },
            bottomRight: { x: 0.95, y: 0.95 }
        };
    }

    /**
     * Create overlay with draggable corners
     */
    createOverlay() {
        // Create canvas overlay
        this.canvas = document.createElement('canvas');
        this.canvas.style.position = 'absolute';
        this.canvas.style.top = '0';
        this.canvas.style.left = '0';
        this.canvas.style.width = '100%';
        this.canvas.style.height = '100%';
        this.canvas.style.cursor = 'crosshair';
        this.canvas.style.touchAction = 'none';
        
        this.ctx = this.canvas.getContext('2d');
        
        // Insert after image
        this.image.parentElement.style.position = 'relative';
        this.image.parentElement.appendChild(this.canvas);
        
        // Match canvas size to image
        this.updateCanvasSize();
        window.addEventListener('resize', () => this.updateCanvasSize());
    }

    /**
     * Update canvas size to match image
     */
    updateCanvasSize() {
        const rect = this.image.getBoundingClientRect();
        this.canvas.width = rect.width;
        this.canvas.height = rect.height;
        this.draw();
    }

    /**
     * Attach mouse and touch events
     */
    attachEvents() {
        // Mouse events
        this.canvas.addEventListener('mousedown', (e) => this.handleStart(e));
        this.canvas.addEventListener('mousemove', (e) => this.handleMove(e));
        this.canvas.addEventListener('mouseup', (e) => this.handleEnd(e));
        
        // Touch events for mobile
        this.canvas.addEventListener('touchstart', (e) => {
            e.preventDefault();
            this.handleStart(e.touches[0]);
        });
        this.canvas.addEventListener('touchmove', (e) => {
            e.preventDefault();
            this.handleMove(e.touches[0]);
        });
        this.canvas.addEventListener('touchend', (e) => {
            e.preventDefault();
            this.handleEnd(e);
        });
    }

    /**
     * Handle start of drag
     */
    handleStart(e) {
        const pos = this.getEventPosition(e);
        const corner = this.findNearestCorner(pos);
        
        if (corner) {
            this.selectedCorner = corner;
            this.isDragging = true;
            this.canvas.style.cursor = 'grabbing';
        }
    }

    /**
     * Handle drag movement
     */
    handleMove(e) {
        if (!this.isDragging || !this.selectedCorner) return;
        
        const pos = this.getEventPosition(e);
        
        // Update corner position (clamped to 0-1)
        this.corners[this.selectedCorner].x = Math.max(0, Math.min(1, pos.x));
        this.corners[this.selectedCorner].y = Math.max(0, Math.min(1, pos.y));
        
        this.draw();
        
        if (this.onUpdate) {
            this.onUpdate(this.corners);
        }
    }

    /**
     * Handle end of drag
     */
    handleEnd(e) {
        this.isDragging = false;
        this.selectedCorner = null;
        this.canvas.style.cursor = 'crosshair';
    }

    /**
     * Get event position in normalized coordinates
     */
    getEventPosition(e) {
        const rect = this.canvas.getBoundingClientRect();
        return {
            x: (e.clientX - rect.left) / rect.width,
            y: (e.clientY - rect.top) / rect.height
        };
    }

    /**
     * Find nearest corner to position
     */
    findNearestCorner(pos) {
        const threshold = 0.08; // 8% of image size
        let nearestCorner = null;
        let minDist = threshold;
        
        for (const [name, corner] of Object.entries(this.corners)) {
            const dist = Math.sqrt(
                Math.pow(corner.x - pos.x, 2) + 
                Math.pow(corner.y - pos.y, 2)
            );
            
            if (dist < minDist) {
                minDist = dist;
                nearestCorner = name;
            }
        }
        
        return nearestCorner;
    }

    /**
     * Draw overlay with corners and guides
     */
    draw() {
        const ctx = this.ctx;
        const width = this.canvas.width;
        const height = this.canvas.height;
        
        // Clear canvas
        ctx.clearRect(0, 0, width, height);
        
        // Draw semi-transparent overlay outside selection
        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.fillRect(0, 0, width, height);
        
        // Clear the selected area
        ctx.globalCompositeOperation = 'destination-out';
        ctx.beginPath();
        ctx.moveTo(this.corners.topLeft.x * width, this.corners.topLeft.y * height);
        ctx.lineTo(this.corners.topRight.x * width, this.corners.topRight.y * height);
        ctx.lineTo(this.corners.bottomRight.x * width, this.corners.bottomRight.y * height);
        ctx.lineTo(this.corners.bottomLeft.x * width, this.corners.bottomLeft.y * height);
        ctx.closePath();
        ctx.fill();
        
        // Reset composite operation
        ctx.globalCompositeOperation = 'source-over';
        
        // Draw border
        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 3;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(this.corners.topLeft.x * width, this.corners.topLeft.y * height);
        ctx.lineTo(this.corners.topRight.x * width, this.corners.topRight.y * height);
        ctx.lineTo(this.corners.bottomRight.x * width, this.corners.bottomRight.y * height);
        ctx.lineTo(this.corners.bottomLeft.x * width, this.corners.bottomLeft.y * height);
        ctx.closePath();
        ctx.stroke();
        
        // Draw corners
        const cornerRadius = 12;
        for (const [name, corner] of Object.entries(this.corners)) {
            const x = corner.x * width;
            const y = corner.y * height;
            
            // Outer circle (white)
            ctx.fillStyle = 'white';
            ctx.beginPath();
            ctx.arc(x, y, cornerRadius, 0, Math.PI * 2);
            ctx.fill();
            
            // Inner circle (green)
            ctx.fillStyle = '#10b981';
            ctx.beginPath();
            ctx.arc(x, y, cornerRadius - 3, 0, Math.PI * 2);
            ctx.fill();
            
            // Corner label (for clarity)
            ctx.fillStyle = 'white';
            ctx.font = 'bold 10px sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            
            const labels = {
                topLeft: 'TL',
                topRight: 'TR',
                bottomLeft: 'BL',
                bottomRight: 'BR'
            };
            ctx.fillText(labels[name], x, y);
        }
    }

    /**
     * Get current corners
     */
    getCorners() {
        return this.corners;
    }

    /**
     * Set update callback
     */
    setOnUpdate(callback) {
        this.onUpdate = callback;
    }

    /**
     * Destroy adjuster and remove overlay
     */
    destroy() {
        if (this.canvas && this.canvas.parentElement) {
            this.canvas.parentElement.removeChild(this.canvas);
        }
    }
}

// Export for use in main app
window.CornerAdjuster = CornerAdjuster;
