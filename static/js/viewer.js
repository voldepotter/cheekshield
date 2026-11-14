/**
 * CheekShield AI — Screenshot Viewer Controller (Section 7 Phase 4)
 *
 * Provides pan & zoom inspection of the returned annotated screenshot:
 *  - Zoom in (+), Zoom out (-), Reset controls
 *  - Wheel & pinch zoom
 *  - Drag-to-pan
 *  - Clickable numbered bounding box overlays matching finding IDs
 *  - Two-way synchronized hover/click linking between boxes and evidence rows
 */

export class ScreenshotViewer {
  constructor(options = {}) {
    this.container = document.getElementById('screenshot-viewer-container');
    this.onBoxHover = options.onBoxHover || (() => {});
    this.onBoxLeave = options.onBoxLeave || (() => {});
    this.onBoxClick = options.onBoxClick || (() => {});

    this.scale = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.isPanning = false;
    this.startX = 0;
    this.startY = 0;

    this.imgWidth = 0;
    this.imgHeight = 0;
  }

  /**
   * Render screenshot viewer if screenshot data exists.
   * @param {Object} result - Normalized API v1 response
   */
  render(result) {
    if (!this.container) return;

    const screenshot = result?.screenshot;
    if (result?.mode !== 'screenshot' || !screenshot?.annotated) {
      this.container.hidden = true;
      this.container.innerHTML = '';
      return;
    }

    this.container.hidden = false;
    this.container.innerHTML = '';
    this.scale = 1.0;
    this.panX = 0;
    this.panY = 0;

    this.imgWidth = screenshot.width || 800;
    this.imgHeight = screenshot.height || 600;

    // 1. Toolbar
    const toolbar = document.createElement('div');
    toolbar.className = 'viewer-toolbar';

    const title = document.createElement('span');
    title.style.fontSize = 'var(--text-xs)';
    title.style.fontWeight = '600';
    title.style.color = 'var(--white-dim)';
    title.textContent = `Screenshot Inspection (${this.imgWidth} × ${this.imgHeight})`;

    const controls = document.createElement('div');
    controls.style.display = 'flex';
    controls.style.alignItems = 'center';
    controls.style.gap = 'var(--space-2)';

    const zoomOutBtn = document.createElement('button');
    zoomOutBtn.type = 'button';
    zoomOutBtn.className = 'receipt-btn';
    zoomOutBtn.style.padding = '4px 10px';
    zoomOutBtn.textContent = '−';
    zoomOutBtn.title = 'Zoom out';
    zoomOutBtn.addEventListener('click', () => this.zoom(-0.2));

    const zoomLabel = document.createElement('span');
    zoomLabel.className = 'viewer-zoom-label';
    zoomLabel.style.fontSize = '11px';
    zoomLabel.style.fontFamily = 'var(--font-mono)';
    zoomLabel.style.minWidth = '44px';
    zoomLabel.style.textAlign = 'center';
    zoomLabel.textContent = '100%';
    this.zoomLabel = zoomLabel;

    const zoomInBtn = document.createElement('button');
    zoomInBtn.type = 'button';
    zoomInBtn.className = 'receipt-btn';
    zoomInBtn.style.padding = '4px 10px';
    zoomInBtn.textContent = '+';
    zoomInBtn.title = 'Zoom in';
    zoomInBtn.addEventListener('click', () => this.zoom(0.2));

    const resetBtn = document.createElement('button');
    resetBtn.type = 'button';
    resetBtn.className = 'receipt-btn';
    resetBtn.style.padding = '4px 10px';
    resetBtn.textContent = 'Reset';
    resetBtn.title = 'Reset view';
    resetBtn.addEventListener('click', () => this.resetView());

    controls.appendChild(zoomOutBtn);
    controls.appendChild(zoomLabel);
    controls.appendChild(zoomInBtn);
    controls.appendChild(resetBtn);

    toolbar.appendChild(title);
    toolbar.appendChild(controls);
    this.container.appendChild(toolbar);

    // 2. Viewport
    const viewport = document.createElement('div');
    viewport.className = 'viewer-viewport';
    this.viewport = viewport;

    const canvasWrap = document.createElement('div');
    canvasWrap.className = 'viewer-canvas-wrap';
    this.canvasWrap = canvasWrap;

    const img = document.createElement('img');
    img.className = 'viewer-img';
    img.src = screenshot.annotated;
    img.alt = 'Annotated screenshot';
    img.draggable = false;

    // Overlay for bounding boxes
    const overlay = document.createElement('div');
    overlay.className = 'viewer-overlay';
    this.overlay = overlay;

    // Inject bounding boxes for findings that have bbox
    const findings = result.findings || [];
    let boxIndex = 1;

    for (const f of findings) {
      if (f.bbox && Array.isArray(f.bbox) && f.bbox.length === 4) {
        const box = this.createBoundingBox(f, boxIndex++);
        overlay.appendChild(box);
      }
    }

    canvasWrap.appendChild(img);
    canvasWrap.appendChild(overlay);
    viewport.appendChild(canvasWrap);
    this.container.appendChild(viewport);

    // Setup pan & zoom listeners
    this.setupInteractions();
  }

  createBoundingBox(finding, displayIndex) {
    const box = document.createElement('div');
    box.className = 'bbox-box';
    box.dataset.findingId = finding.id;
    box.tabIndex = 0;
    box.title = `${finding.category}: ${finding.text?.slice(0, 50)}...`;

    // Coordinates: [x1, y1, x2, y2]
    const [x1, y1, x2, y2] = finding.bbox;
    const leftPct = ((x1 / this.imgWidth) * 100).toFixed(2);
    const topPct = ((y1 / this.imgHeight) * 100).toFixed(2);
    const widthPct = (((x2 - x1) / this.imgWidth) * 100).toFixed(2);
    const heightPct = (((y2 - y1) / this.imgHeight) * 100).toFixed(2);

    box.style.left = `${leftPct}%`;
    box.style.top = `${topPct}%`;
    box.style.width = `${widthPct}%`;
    box.style.height = `${heightPct}%`;

    // Badge label
    const badge = document.createElement('span');
    badge.className = 'bbox-badge';
    badge.textContent = String(displayIndex);
    box.appendChild(badge);

    // Events
    box.addEventListener('mouseenter', () => {
      this.onBoxHover(finding.id);
    });
    box.addEventListener('mouseleave', () => {
      this.onBoxLeave(finding.id);
    });
    box.addEventListener('click', (e) => {
      e.stopPropagation();
      this.onBoxClick(finding.id);
    });
    box.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.onBoxClick(finding.id);
      }
    });

    return box;
  }

  setupInteractions() {
    if (!this.viewport) return;

    // Pan with mouse drag
    this.viewport.addEventListener('mousedown', (e) => {
      if (e.target.closest('.bbox-box')) return;
      this.isPanning = true;
      this.startX = e.clientX - this.panX;
      this.startY = e.clientY - this.panY;
      this.viewport.style.cursor = 'grabbing';
    });

    window.addEventListener('mousemove', (e) => {
      if (!this.isPanning) return;
      this.panX = e.clientX - this.startX;
      this.panY = e.clientY - this.startY;
      this.updateTransform();
    });

    window.addEventListener('mouseup', () => {
      if (this.isPanning) {
        this.isPanning = false;
        if (this.viewport) this.viewport.style.cursor = 'grab';
      }
    });

    // Wheel zoom
    this.viewport.addEventListener('wheel', (e) => {
      e.preventDefault();
      const delta = e.deltaY < 0 ? 0.15 : -0.15;
      this.zoom(delta);
    }, { passive: false });
  }

  zoom(delta) {
    const newScale = Math.max(0.5, Math.min(3.5, this.scale + delta));
    this.scale = newScale;
    if (this.zoomLabel) {
      this.zoomLabel.textContent = `${Math.round(this.scale * 100)}%`;
    }
    this.updateTransform();
  }

  resetView() {
    this.scale = 1.0;
    this.panX = 0;
    this.panY = 0;
    if (this.zoomLabel) {
      this.zoomLabel.textContent = '100%';
    }
    this.updateTransform();
  }

  updateTransform() {
    if (!this.canvasWrap) return;
    this.canvasWrap.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.scale})`;
  }

  highlightBox(findingId) {
    if (!this.overlay) return;
    const boxes = this.overlay.querySelectorAll('.bbox-box');
    boxes.forEach((b) => {
      const match = b.dataset.findingId === findingId;
      b.classList.toggle('highlighted', match);
    });
  }

  clearBoxHighlight() {
    if (!this.overlay) return;
    const boxes = this.overlay.querySelectorAll('.bbox-box.highlighted');
    boxes.forEach((b) => b.classList.remove('highlighted'));
  }

  focusBox(findingId) {
    this.highlightBox(findingId);
    if (!this.overlay) return;
    const box = this.overlay.querySelector(`.bbox-box[data-finding-id="${findingId}"]`);
    if (box) {
      // Pulse animation
      box.classList.remove('pulse');
      void box.offsetWidth;
      box.classList.add('pulse');
    }
  }
}
