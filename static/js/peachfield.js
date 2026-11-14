/**
 * CheekShield AI — Peach Field (Animated Canvas Background, Section 6.10)
 */

export const GRID_ALPHA = 0.14;
export const FLOATER_ALPHA = 0.24;

export class PeachField {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.speedMultiplier = 1.0;
    this.isAuditing = false;
    this.animId = null;
    this.lastTime = 0;
    this.fps = 30;
    this.fpsInterval = 1000 / this.fps;

    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.width = 0;
    this.height = 0;
    this.dpr = 1;

    // Grid animation offsets
    this.offsetX = 0;
    this.offsetY = 0;

    // Floaters: 6 to 10 peaches drifting upward
    this.floaters = [];

    // Pre-rendered peach sprite
    this.spriteCanvas = document.createElement('canvas');
    this.spriteSize = 22;
    this.renderPeachSprite();

    this.init();
  }

  renderPeachSprite() {
    const size = this.spriteSize;
    this.spriteCanvas.width = size;
    this.spriteCanvas.height = size;
    const sctx = this.spriteCanvas.getContext('2d');

    // Draw tiny peach
    // Path scaled from meter outline
    sctx.save();
    sctx.translate(size / 2, size / 2);
    const scale = size / 280;
    sctx.scale(scale, scale);
    sctx.translate(-120, -140);

    // Peach body
    sctx.fillStyle = '#FF8A3D';
    sctx.beginPath();
    // M120 44 C 80 20, 18 48, 18 128 C 18 196, 66 252, 120 252 C 174 252, 222 196, 222 128 C 222 48, 160 20, 120 44 Z
    sctx.moveTo(120, 44);
    sctx.bezierCurveTo(80, 20, 18, 48, 18, 128);
    sctx.bezierCurveTo(18, 196, 66, 252, 120, 252);
    sctx.bezierCurveTo(174, 252, 222, 196, 222, 128);
    sctx.bezierCurveTo(222, 48, 160, 20, 120, 44);
    sctx.closePath();
    sctx.fill();

    // Leaf
    sctx.fillStyle = '#7BD389';
    sctx.beginPath();
    sctx.moveTo(120, 44);
    sctx.bezierCurveTo(135, 15, 160, 20, 165, 35);
    sctx.bezierCurveTo(155, 45, 135, 45, 120, 44);
    sctx.fill();

    sctx.restore();
  }

  init() {
    this.resize();
    this.initFloaters();

    window.addEventListener('resize', () => this.debounceResize());
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        this.stop();
      } else if (!this.reducedMotion) {
        this.start();
      }
    });

    if (this.reducedMotion) {
      this.drawFrame();
    } else {
      this.start();
    }
  }

  initFloaters() {
    const count = this.width < 760 ? 6 : 9;
    this.floaters = [];
    for (let i = 0; i < count; i++) {
      this.floaters.push({
        x: Math.random() * this.width,
        y: Math.random() * this.height,
        speed: 10 + Math.random() * 14, // px/s
        scale: 0.8 + Math.random() * 0.5,
        opacity: FLOATER_ALPHA * (0.88 + Math.random() * 0.24), // target 0.22 - 0.26
        rotation: (Math.random() - 0.5) * 0.4,
      });
    }
  }

  debounceResize() {
    clearTimeout(this.resizeTimer);
    this.resizeTimer = setTimeout(() => {
      this.resize();
      this.initFloaters();
      if (this.reducedMotion) this.drawFrame();
    }, 150);
  }

  resize() {
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.width = window.innerWidth;
    this.height = window.innerHeight;
    this.canvas.width = this.width * this.dpr;
    this.canvas.height = this.height * this.dpr;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  }

  setAuditing(auditing) {
    this.isAuditing = auditing;
    this.speedMultiplier = auditing ? 2.0 : 1.0;
  }

  start() {
    if (this.animId) return;
    this.lastTime = performance.now();
    const loop = (now) => {
      this.animId = requestAnimationFrame(loop);
      const elapsed = now - this.lastTime;
      if (elapsed > this.fpsInterval) {
        const delta = Math.min(elapsed / 1000, 0.1);
        this.lastTime = now - (elapsed % this.fpsInterval);
        this.update(delta);
        this.drawFrame();
      }
    };
    this.animId = requestAnimationFrame(loop);
  }

  stop() {
    if (this.animId) {
      cancelAnimationFrame(this.animId);
      this.animId = null;
    }
  }

  update(delta) {
    const baseSpeed = 6 * this.speedMultiplier; // 6 px/s base diagonal
    this.offsetX = (this.offsetX + baseSpeed * delta) % 112;
    this.offsetY = (this.offsetY + baseSpeed * delta) % 112;

    // Update floaters
    for (const f of this.floaters) {
      f.y -= f.speed * this.speedMultiplier * delta;
      if (f.y < -30) {
        f.y = this.height + 30;
        f.x = Math.random() * this.width;
      }
    }
  }

  drawFrame() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);

    const isMobile = this.width < 760;
    const spacing = isMobile ? 44 : 56;
    const size = this.spriteSize;

    // 1. Brick-offset grid (raised opacity)
    ctx.save();
    ctx.globalAlpha = GRID_ALPHA;

    const startX = -spacing + (this.offsetX % spacing);
    const startY = -spacing + (this.offsetY % spacing);

    let row = 0;
    for (let y = startY - spacing; y < this.height + spacing * 2; y += spacing) {
      const offsetX = (row % 2 === 1) ? spacing / 2 : 0;
      let col = 0;
      for (let x = startX - spacing; x < this.width + spacing * 2; x += spacing) {
        const px = x + offsetX;
        // Deterministic tiny variance based on row/col
        const seed = Math.sin(row * 12.9898 + col * 78.233) * 43758.5453;
        const rot = ((seed % 1) - 0.5) * 0.25;

        ctx.save();
        ctx.translate(px, y);
        ctx.rotate(rot);
        ctx.drawImage(this.spriteCanvas, -size / 2, -size / 2, size, size);
        ctx.restore();
        col++;
      }
      row++;
    }
    ctx.restore();

    // 2. Floaters (~12% opacity drifting up)
    ctx.save();
    for (const f of this.floaters) {
      ctx.globalAlpha = f.opacity;
      ctx.save();
      ctx.translate(f.x, f.y);
      ctx.rotate(f.rotation);
      const fs = size * f.scale;
      ctx.drawImage(this.spriteCanvas, -fs / 2, -fs / 2, fs, fs);
      ctx.restore();
    }
    ctx.restore();

    // 3. Radial vignette: darker at the edges, center calmer
    const cx = this.width / 2;
    const cy = this.height / 2;
    const radius = Math.max(this.width, this.height) * 0.7;
    const vignette = ctx.createRadialGradient(cx, cy, radius * 0.2, cx, cy, radius);
    vignette.addColorStop(0, 'rgba(0, 0, 0, 0)');
    vignette.addColorStop(1, 'rgba(0, 0, 0, 0.45)');

    ctx.fillStyle = vignette;
    ctx.fillRect(0, 0, this.width, this.height);
  }
}
