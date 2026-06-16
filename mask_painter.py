"""Mask painter popup for Topaz API object removal.

Launches a browser-based mask painter over frame 1 of the clip.
User paints white (areas to remove) over the frame, clicks Save,
and the mask PNG is saved to disk for the Topaz API.

Usage (standalone test):
    python3 mask_painter.py /path/to/frame.png /path/to/output_mask.png

Usage (from engine):
    from mask_painter import launch_mask_painter
    mask_path = launch_mask_painter(frame_png_path, output_mask_path)
"""
import sys
import os
import base64
import json
import threading
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler


def _build_html(frame_b64, width, height):
    """Generate the mask painter HTML with the frame embedded."""
    return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Topaz Mask Painter</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #1a1a2e; color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    display: flex; flex-direction: column; align-items: center;
    min-height: 100vh; padding: 20px;
}
h1 { font-size: 18px; margin-bottom: 12px; color: #8be9fd; }
.toolbar {
    display: flex; gap: 16px; align-items: center;
    margin-bottom: 12px; padding: 10px 20px;
    background: #16213e; border-radius: 8px;
}
.toolbar label { font-size: 13px; color: #aaa; }
.toolbar input[type=range] { width: 120px; cursor: pointer; }
.toolbar button {
    padding: 8px 20px; border: none; border-radius: 6px;
    font-size: 14px; font-weight: 600; cursor: pointer;
    transition: all 0.2s;
}
.btn-clear { background: #e74c3c; color: #fff; }
.btn-clear:hover { background: #c0392b; }
.btn-save { background: #2ecc71; color: #fff; }
.btn-save:hover { background: #27ae60; }
.btn-eraser { background: #3498db; color: #fff; }
.btn-eraser:hover { background: #2980b9; }
.btn-eraser.active { background: #e67e22; }
.canvas-wrap {
    position: relative; display: inline-block;
    border: 2px solid #333; border-radius: 4px;
    cursor: crosshair;
}
canvas { display: block; }
#overlay { position: absolute; top: 0; left: 0; }
.brush-preview {
    position: fixed; pointer-events: none;
    border: 2px solid rgba(255,255,255,0.6);
    border-radius: 50%; transform: translate(-50%, -50%);
    z-index: 100;
}
.status {
    margin-top: 12px; font-size: 13px; color: #888;
}
</style>
</head>
<body>
<h1>Paint mask over areas to remove (cyan overlay → saved as white)</h1>
<div class="toolbar">
    <label>Brush: <span id="sizeLabel">30</span>px</label>
    <input type="range" id="brushSize" min="3" max="150" value="30">
    <button class="btn-eraser" id="eraserBtn" onclick="toggleEraser()">Eraser</button>
    <button class="btn-clear" onclick="clearMask()">Clear</button>
    <button class="btn-save" onclick="saveMask()">Save Mask</button>
</div>
<div class="canvas-wrap">
    <canvas id="bg" width="WIDTH" height="HEIGHT"></canvas>
    <canvas id="overlay" width="WIDTH" height="HEIGHT"></canvas>
</div>
<div class="brush-preview" id="brushPreview"></div>
<div class="status" id="status">Paint the areas you want to remove, then click Save Mask</div>

<script>
const W = WIDTH, H = HEIGHT;
const bgCanvas = document.getElementById('bg');
const bgCtx = bgCanvas.getContext('2d');
const overlay = document.getElementById('overlay');
const ctx = overlay.getContext('2d');
const brushSlider = document.getElementById('brushSize');
const sizeLabel = document.getElementById('sizeLabel');
const preview = document.getElementById('brushPreview');
const status = document.getElementById('status');

let painting = false;
let erasing = false;
let brushSize = 30;
// Separate tracking: drawX/drawY for canvas coords, previewX/previewY for screen coords
let drawX = 0, drawY = 0;

// Load background frame
const img = new Image();
img.onload = () => bgCtx.drawImage(img, 0, 0, W, H);
img.src = 'data:image/png;base64,FRAME_B64';

// Paint color: semi-transparent cyan so user can see through
const PAINT_COLOR = 'rgba(0, 220, 255, 0.35)';
const PAINT_ALPHA = 0.35;

brushSlider.oninput = () => {
    brushSize = parseInt(brushSlider.value);
    sizeLabel.textContent = brushSize;
};

// Get canvas-relative coords, accounting for CSS scaling
function canvasCoords(e) {
    const r = overlay.getBoundingClientRect();
    const scaleX = W / r.width;
    const scaleY = H / r.height;
    return {
        x: (e.clientX - r.left) * scaleX,
        y: (e.clientY - r.top) * scaleY
    };
}

overlay.addEventListener('mousedown', (e) => {
    painting = true;
    const c = canvasCoords(e);
    drawX = c.x;
    drawY = c.y;
    drawDot(drawX, drawY);
});

overlay.addEventListener('mousemove', (e) => {
    // Update brush preview (screen coords)
    preview.style.left = e.clientX + 'px';
    preview.style.top = e.clientY + 'px';
    preview.style.width = brushSize + 'px';
    preview.style.height = brushSize + 'px';

    if (!painting) return;
    const c = canvasCoords(e);
    drawLine(drawX, drawY, c.x, c.y);
    drawX = c.x;
    drawY = c.y;
});

overlay.addEventListener('mouseup', () => painting = false);
overlay.addEventListener('mouseleave', () => painting = false);

// Update preview when moving outside canvas too
document.addEventListener('mousemove', (e) => {
    preview.style.left = e.clientX + 'px';
    preview.style.top = e.clientY + 'px';
    preview.style.width = brushSize + 'px';
    preview.style.height = brushSize + 'px';
});

function drawDot(x, y) {
    if (erasing) {
        ctx.globalCompositeOperation = 'destination-out';
        ctx.globalAlpha = 1;
        ctx.fillStyle = '#000';
    } else {
        ctx.globalCompositeOperation = 'source-over';
        ctx.globalAlpha = PAINT_ALPHA;
        ctx.fillStyle = PAINT_COLOR;
    }
    ctx.beginPath();
    ctx.arc(x, y, brushSize / 2, 0, Math.PI * 2);
    ctx.fill();
}

function drawLine(x1, y1, x2, y2) {
    if (erasing) {
        ctx.globalCompositeOperation = 'destination-out';
        ctx.globalAlpha = 1;
        ctx.strokeStyle = '#000';
    } else {
        ctx.globalCompositeOperation = 'source-over';
        ctx.globalAlpha = PAINT_ALPHA;
        ctx.strokeStyle = PAINT_COLOR;
    }
    ctx.lineWidth = brushSize;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
}

function toggleEraser() {
    erasing = !erasing;
    document.getElementById('eraserBtn').classList.toggle('active', erasing);
    document.getElementById('eraserBtn').textContent = erasing ? 'Painting' : 'Eraser';
}

function clearMask() {
    ctx.globalCompositeOperation = 'source-over';
    ctx.clearRect(0, 0, W, H);
}

function saveMask() {
    // Create a B/W mask: white where painted, black where not
    const maskCanvas = document.createElement('canvas');
    maskCanvas.width = W;
    maskCanvas.height = H;
    const mCtx = maskCanvas.getContext('2d');

    // Start with black
    mCtx.fillStyle = '#000';
    mCtx.fillRect(0, 0, W, H);

    // Get overlay pixel data -- any non-transparent pixel = white in mask
    const overlayData = ctx.getImageData(0, 0, W, H);
    const maskData = mCtx.getImageData(0, 0, W, H);
    for (let i = 3; i < overlayData.data.length; i += 4) {
        if (overlayData.data[i] > 0) {
            maskData.data[i - 3] = 255; // R
            maskData.data[i - 2] = 255; // G
            maskData.data[i - 1] = 255; // B
            maskData.data[i] = 255;     // A
        }
    }
    mCtx.putImageData(maskData, 0, 0);

    // Send to server
    const dataUrl = maskCanvas.toDataURL('image/png');
    const b64 = dataUrl.split(',')[1];

    status.textContent = 'Saving mask...';
    fetch('/save_mask', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({mask_b64: b64})
    })
    .then(r => r.json())
    .then(d => {
        status.textContent = 'Mask saved! You can close this tab.';
        status.style.color = '#2ecc71';
    })
    .catch(e => {
        status.textContent = 'Error saving mask: ' + e;
        status.style.color = '#e74c3c';
    });
}
</script>
</body>
</html>""".replace('WIDTH', str(width)).replace('HEIGHT', str(height)).replace('FRAME_B64', frame_b64)


class _MaskHandler(BaseHTTPRequestHandler):
    """HTTP handler for the mask painter."""

    output_path = None
    mask_saved = threading.Event()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(self.server.html_content.encode('utf-8'))

    def do_POST(self):
        if self.path == '/save_mask':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body)
            mask_b64 = data['mask_b64']
            mask_bytes = base64.b64decode(mask_b64)
            with open(_MaskHandler.output_path, 'wb') as f:
                f.write(mask_bytes)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            _MaskHandler.mask_saved.set()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress server logs


def launch_mask_painter(frame_png_path, output_mask_path, _log=None):
    """Launch a browser-based mask painter over the given frame.

    Blocks until the user saves the mask. Returns the output mask path,
    or None if the user closes without saving (timeout 10 min).
    """
    if _log:
        _log("  Opening mask painter in browser...")

    # Read frame and encode as base64
    with open(frame_png_path, 'rb') as f:
        frame_b64 = base64.b64encode(f.read()).decode('ascii')

    # Get frame dimensions
    from PIL import Image
    img = Image.open(frame_png_path)
    width, height = img.size
    img.close()

    # Cap display size for large frames (scale to fit 1280px wide)
    display_w, display_h = width, height
    if width > 1280:
        scale = 1280 / width
        display_w = 1280
        display_h = int(height * scale)

    html = _build_html(frame_b64, display_w, display_h)

    # Set output path
    _MaskHandler.output_path = output_mask_path
    _MaskHandler.mask_saved.clear()

    # Start server on a random available port
    server = HTTPServer(('127.0.0.1', 0), _MaskHandler)
    server.html_content = html
    port = server.server_address[1]

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Open browser
    url = 'http://127.0.0.1:%d' % port
    subprocess.Popen(['open', url])

    if _log:
        _log("  Mask painter opened at %s" % url)
        _log("  Paint the areas to remove, then click 'Save Mask'")

    # Wait for mask to be saved (timeout 10 minutes)
    saved = _MaskHandler.mask_saved.wait(timeout=600)

    server.shutdown()

    if saved and os.path.exists(output_mask_path):
        if _log:
            _log("  Mask saved: %s" % output_mask_path)
        return output_mask_path
    else:
        if _log:
            _log("  Mask painter closed without saving")
        return None


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 mask_painter.py <frame.png> <output_mask.png>")
        sys.exit(1)
    result = launch_mask_painter(sys.argv[1], sys.argv[2],
                                 _log=lambda msg: print(msg))
    if result:
        print("Mask saved to: %s" % result)
    else:
        print("No mask saved")
