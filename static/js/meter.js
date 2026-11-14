/**
 * CheekShield AI — Peach Outcome Controller
 *
 * Implements the two-outcome peach indicator:
 *  - Nothing detected: peach stays empty, checkmark tick, side text "Fresh"
 *  - Anything detected: peach fills slowly over 3.2s to the very top (covering
 *    every pixel including both upper lobes beside the cleft dip), then runs
 *    a gentle breathing pulse loop in a slightly reddish tone, with side text
 *    "Soft spots detected" and sub-line "Review each finding below."
 *
 * Fully respects prefers-reduced-motion: reduce (static render, no fill/wave/pulse).
 */

const LOADING_MESSAGES = [
  'Cheeko is reading the page',
  'Looking for pressure words',
  'Checking buttons and boxes',
  'Weighing the evidence',
];

// SVG viewBox 0 0 240 280
// Peach shape:
//  - Top cleft dip at Y=44
//  - Upper lobes peak at Y≈22-24
//  - Bottom tip at Y=252
// Full level must sit above topmost lobe so every pixel is covered
const PEACH_FULL_Y = 10;
const PEACH_EMPTY_Y = 256;
const FILL_DURATION_MS = 3200; // 3.2s ease-in-out fill
const DRAIN_DURATION_MS = 800; // 0.8s drain for clean
const PULSE_PERIOD_MS = 2400;  // 2.4s breathing loop

// Single helper for the outcome:
// response.summary.flagged_items > 0
export function isFlagged(response) {
  if (!response) return false;
  const flagged = response.summary?.flagged_items;
  if (typeof flagged === 'number') {
    return flagged > 0;
  }
  const findings = response.findings || [];
  return findings.some((f) => f.kind === 'flag');
}

function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// Blend between --peach (#FF8A3D) and --peach-hot (#FF4D1C)
// ratio = 0 -> #FF8A3D (rgb 255, 138, 61)
// ratio = 1 -> #FF4D1C (rgb 255, 77, 28)
function blendPeachHot(ratio) {
  const r = Math.max(0, Math.min(1, ratio));
  const g = Math.round(138 - 61 * r);
  const b = Math.round(61 - 33 * r);
  return `rgb(255, ${g}, ${b})`;
}

export class MeterController {
  constructor() {
    // DOM elements
    this.svgBox = document.getElementById('meter-svg-box');
    this.svgEl = document.getElementById('meter-svg');
    this.waveFront = document.getElementById('meter-wave-front');
    this.waveBack = document.getElementById('meter-wave-back');
    this.fluidGroup = document.getElementById('meter-fluid-group');
    this.peachOutline = document.getElementById('meter-peach-outline');
    this.cleanTick = document.getElementById('meter-clean-tick');
    this.bandEl = document.getElementById('meter-band');
    this.explainerEl = document.getElementById('meter-explainer');
    this.a11yStatus = document.getElementById('a11y-status');

    // Gradient stops in SVG defs
    this.gradientStops = document.querySelectorAll('#fluid-grad stop');

    // State: 'idle' | 'analyzing' | 'flagged' | 'clean' | 'error'
    this.state = 'idle';

    // Fluid level (Y coordinate in SVG space: 10 = full, 256 = empty)
    this.currentY = PEACH_EMPTY_Y;
    this.targetY = PEACH_EMPTY_Y;

    // Fill animation state (flagged)
    this.fillStartTime = 0;
    this.fillStartY = PEACH_EMPTY_Y;
    this.isFilling = false;
    this.waveAmplitudeStart = 6;

    // Drain animation state (clean)
    this.drainStartTime = 0;
    this.drainStartY = PEACH_EMPTY_Y;
    this.isDraining = false;

    // Pulse loop state (after fill completes)
    this.isPulsing = false;
    this.pulseStartTime = 0;

    // Wave parameters
    this.wavePhase = 0;
    this.waveAmplitude = 4;
    this.bobPhase = 0;

    // Analyzing slosh
    this.analyzePhase = 0;

    // Loading message rotation
    this.loadingMsgIndex = 0;
    this.loadingMsgTimer = null;

    // Animation frame
    this.animFrame = null;
    this.lastTime = 0;
    this.running = false;

    // Decorative juice elements
    this.bubbles = [];
    this.streaks = [];

    this.init();
  }

  init() {
    // Easter egg: wobble on click
    if (this.svgBox) {
      this.svgBox.addEventListener('click', () => this.wobble());
    }

    // Listen for audit lifecycle events
    window.addEventListener('cheek:audit-start', () => this.setAnalyzing());
    window.addEventListener('cheek:audit-cancel', () => this.setIdle());
    window.addEventListener('cheek:audit-error', (e) => this.setError(e.detail));

    // Visibility change — pause/resume
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        this.stop();
      } else {
        this.start();
      }
    });

    // Initialize streaks and bubbles
    this.initStreaks();
    this.initBubbles();

    // Start in idle
    this.setIdle();
    this.start();
  }

  // =====================================================================
  // Animation Loop
  // =====================================================================
  start() {
    if (this.running) return;
    this.running = true;
    this.lastTime = performance.now();
    this.tick(this.lastTime);
  }

  stop() {
    this.running = false;
    if (this.animFrame) {
      cancelAnimationFrame(this.animFrame);
      this.animFrame = null;
    }
  }

  tick(now) {
    if (!this.running) return;

    const dt = Math.min(Math.max(0, (now - this.lastTime) / 1000), 0.05);
    this.lastTime = now;

    if (prefersReducedMotion()) {
      this.renderReducedMotion();
    } else {
      this.updateStateLogic(now, dt);
      this.updateBubbles(dt);
      this.wavePhase += dt * 2.5;
      this.bobPhase += dt;
      this.renderWaves();
    }

    this.animFrame = requestAnimationFrame((t) => this.tick(t));
  }

  // =====================================================================
  // State Logic & Physics Updates
  // =====================================================================
  updateStateLogic(now, dt) {
    if (this.state === 'analyzing') {
      // Indeterminate slosh between Y ≈ 165 and Y ≈ 205
      this.analyzePhase += dt * 1.6;
      const sloshTarget = 185 + 20 * Math.sin(this.analyzePhase);
      // Smoothly ease currentY from wherever it started to the slosh target
      this.currentY += (sloshTarget - this.currentY) * Math.min(1, dt * 3.5);
      this.waveAmplitude = 9;
      this.resetGradientToNormal();
      return;
    }

    if (this.state === 'flagged') {
      if (this.isFilling) {
        const elapsed = now - this.fillStartTime;
        const progress = Math.min(1, elapsed / FILL_DURATION_MS);
        // Cosine ease-in-out curve: strictly no overshoot
        const ease = (1 - Math.cos(progress * Math.PI)) / 2;
        this.currentY = this.fillStartY + (PEACH_FULL_Y - this.fillStartY) * ease;

        // Wave amplitude decays as fluid fills
        this.waveAmplitude = Math.max(1.2, this.waveAmplitudeStart * (1 - 0.8 * ease));

        // Gradient shifts toward reddish
        // Top: --peach (#FF8A3D)
        // Mid: shifts up to 60% --peach-hot
        // Bot: --peach-hot (#FF4D1C)
        const midBlend = 0.6 * ease;
        this.setGradientStops('#FF8A3D', blendPeachHot(midBlend), '#FF4D1C');

        if (progress >= 1) {
          this.isFilling = false;
          this.currentY = PEACH_FULL_Y;
          this.waveAmplitude = 1.0;
          this.startPulse(now);
        }
      } else if (this.isPulsing) {
        // Continuous slow breathing loop (period 2.4s)
        const pulseElapsed = now - this.pulseStartTime;
        const phi = (2 * Math.PI * pulseElapsed) / PULSE_PERIOD_MS;
        const s = (1 + Math.sin(phi)) / 2; // oscillates 0 -> 1 -> 0

        // 1. Oscillate red blend between 50% and 85%
        const midBlend = 0.5 + 0.35 * s;
        this.setGradientStops('#FF8A3D', blendPeachHot(midBlend), '#FF4D1C');

        // 2. Faint orange-red glow around outline (alpha 0.25 to 0.50)
        const glowAlpha = 0.25 + 0.25 * s;
        if (this.peachOutline) {
          this.peachOutline.style.filter = `drop-shadow(0 0 6px rgba(255, 77, 28, ${glowAlpha.toFixed(2)}))`;
        }

        // 3. Subtle scale between 1.00 and 1.012
        const scale = 1.0 + 0.012 * s;
        if (this.svgEl) {
          this.svgEl.style.transform = `scale(${scale.toFixed(4)})`;
          this.svgEl.style.transformOrigin = '120px 140px';
        }

        this.currentY = PEACH_FULL_Y;
        this.waveAmplitude = 1.0;
      }
      return;
    }

    if (this.state === 'clean') {
      if (this.isDraining) {
        const elapsed = now - this.drainStartTime;
        const progress = Math.min(1, elapsed / DRAIN_DURATION_MS);
        // Ease-out drain
        const ease = 1 - Math.pow(1 - progress, 2);
        this.currentY = this.drainStartY + (PEACH_EMPTY_Y - this.drainStartY) * ease;
        this.waveAmplitude = Math.max(1, 4 * (1 - ease));

        if (progress >= 1) {
          this.isDraining = false;
          this.currentY = PEACH_EMPTY_Y;
          this.waveAmplitude = 3;
          this.showCleanTick();
        }
      } else {
        this.currentY = PEACH_EMPTY_Y;
        this.waveAmplitude = 3;
      }
      this.resetGradientToNormal();
      return;
    }

    if (this.state === 'idle' || this.state === 'error') {
      this.currentY = PEACH_EMPTY_Y;
      this.waveAmplitude = 4;
      this.resetGradientToNormal();
    }
  }

  // =====================================================================
  // Wave Rendering
  // =====================================================================
  renderWaves() {
    let baseY = this.currentY;

    // Gentle bob in idle or clean-drained states
    if ((this.state === 'idle' || (this.state === 'clean' && !this.isDraining)) && !prefersReducedMotion()) {
      baseY += Math.sin(this.bobPhase * (Math.PI / 2)) * 3; // ~3px, ~4s period
    }

    const amp = this.waveAmplitude;

    // Front wave
    const frontPath = this.buildWavePath(baseY, amp, this.wavePhase, 0.04);
    // Back wave (different phase and slightly offset)
    const backPath = this.buildWavePath(baseY + 2, amp * 0.7, this.wavePhase + 2.0, 0.035);

    if (this.waveFront) this.waveFront.setAttribute('d', frontPath);
    if (this.waveBack) this.waveBack.setAttribute('d', backPath);

    // Render decorative juice elements inside fluid
    this.renderStreaks(baseY);
  }

  buildWavePath(baseY, amplitude, phase, frequency) {
    const width = 240;
    const segments = 24;
    const step = width / segments;

    let d = `M 0 ${baseY.toFixed(1)}`;
    for (let i = 0; i <= segments; i++) {
      const x = i * step;
      const waveY = baseY + amplitude * Math.sin(frequency * x * 10 + phase);
      d += ` L ${x.toFixed(1)} ${waveY.toFixed(1)}`;
    }
    // Close below viewBox bottom
    d += ` L 240 280 L 0 280 Z`;
    return d;
  }

  // =====================================================================
  // Reduced Motion Render
  // =====================================================================
  renderReducedMotion() {
    if (this.state === 'flagged') {
      this.currentY = PEACH_FULL_Y;
      const frontPath = `M 0 ${PEACH_FULL_Y} L 240 ${PEACH_FULL_Y} L 240 280 L 0 280 Z`;
      if (this.waveFront) this.waveFront.setAttribute('d', frontPath);
      if (this.waveBack) this.waveBack.setAttribute('d', frontPath);
      this.setGradientStops('#FF8A3D', blendPeachHot(0.6), '#FF4D1C');
      if (this.peachOutline) {
        this.peachOutline.style.filter = 'none';
        this.peachOutline.setAttribute('stroke', '#FF8A3D');
        this.peachOutline.removeAttribute('stroke-dasharray');
      }
      if (this.svgEl) this.svgEl.style.transform = 'scale(1)';
    } else {
      this.currentY = PEACH_EMPTY_Y;
      const emptyPath = `M 0 280 L 240 280 L 240 280 L 0 280 Z`;
      if (this.waveFront) this.waveFront.setAttribute('d', emptyPath);
      if (this.waveBack) this.waveBack.setAttribute('d', emptyPath);
      this.resetGradientToNormal();
      if (this.svgEl) this.svgEl.style.transform = 'scale(1)';
      if (this.peachOutline) this.peachOutline.style.filter = 'none';
    }
  }

  // =====================================================================
  // Gradient Helpers
  // =====================================================================
  setGradientStops(stop0, stop1, stop2) {
    if (!this.gradientStops || this.gradientStops.length < 3) return;
    this.gradientStops[0].setAttribute('stop-color', stop0);
    this.gradientStops[1].setAttribute('stop-color', stop1);
    this.gradientStops[2].setAttribute('stop-color', stop2);
  }

  resetGradientToNormal() {
    this.setGradientStops('#FFB784', '#FF8A3D', '#FF4D1C');
    if (this.waveBack) {
      this.waveBack.setAttribute('fill', '#FF8A3D');
      this.waveBack.setAttribute('opacity', '0.5');
    }
  }

  // =====================================================================
  // Pulse Loop Control
  // =====================================================================
  startPulse(startTime) {
    this.isPulsing = true;
    this.pulseStartTime = startTime || performance.now();
  }

  stopPulse() {
    this.isPulsing = false;
    this.isFilling = false;
    if (this.peachOutline) {
      this.peachOutline.style.filter = 'none';
    }
    if (this.svgEl) {
      this.svgEl.style.transform = 'scale(1)';
    }
  }

  // =====================================================================
  // Juice Streaks & Bubbles
  // =====================================================================
  initStreaks() {
    this.streaks = [];
    if (!this.fluidGroup) return;
    for (let i = 0; i < 5; i++) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('stroke', '#FF4D1C');
      line.setAttribute('stroke-width', '1');
      line.setAttribute('opacity', '0.15');
      line.setAttribute('stroke-linecap', 'round');
      this.fluidGroup.appendChild(line);
      this.streaks.push({
        el: line,
        x: 40 + i * 40 + (Math.random() - 0.5) * 20,
        lengthFactor: 0.3 + Math.random() * 0.4,
      });
    }
  }

  renderStreaks(fluidTop) {
    const bottom = 270;
    for (const streak of this.streaks) {
      const height = (bottom - fluidTop) * streak.lengthFactor;
      if (height < 5 || fluidTop > 250) {
        streak.el.setAttribute('opacity', '0');
        continue;
      }
      streak.el.setAttribute('opacity', '0.12');
      streak.el.setAttribute('x1', streak.x);
      streak.el.setAttribute('y1', fluidTop + 8);
      streak.el.setAttribute('x2', streak.x);
      streak.el.setAttribute('y2', fluidTop + 8 + height);
    }
  }

  initBubbles() {
    this.bubbles = [];
    if (!this.fluidGroup) return;
    for (let i = 0; i < 6; i++) {
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('fill', '#FFFFFF');
      circle.setAttribute('opacity', '0');
      this.fluidGroup.appendChild(circle);
      this.bubbles.push({
        el: circle,
        x: 0,
        y: 0,
        r: 0,
        speed: 0,
        alive: false,
        life: 0,
      });
    }
  }

  updateBubbles(dt) {
    const fluidTop = this.currentY;
    const hasFluid = fluidTop < 245;

    for (const b of this.bubbles) {
      if (!b.alive) {
        if (hasFluid && Math.random() < dt * 0.8) {
          b.alive = true;
          b.x = 40 + Math.random() * 160;
          b.y = 245;
          b.r = 1.5 + Math.random() * 2;
          b.speed = 20 + Math.random() * 25;
          b.life = 0;
          b.el.setAttribute('r', b.r);
        }
        continue;
      }

      b.y -= b.speed * dt;
      b.x += Math.sin(b.life * 4) * 8 * dt;
      b.life += dt;

      if (b.y < fluidTop + 5 || b.life > 4) {
        b.alive = false;
        b.el.setAttribute('opacity', '0');
        continue;
      }

      b.el.setAttribute('cx', b.x.toFixed(1));
      b.el.setAttribute('cy', b.y.toFixed(1));
      const distToSurface = b.y - fluidTop;
      const alpha = Math.min(0.3, distToSurface / 60);
      b.el.setAttribute('opacity', alpha.toFixed(2));
    }
  }

  // =====================================================================
  // State Transitions
  // =====================================================================
  setIdle() {
    this.stopPulse();
    this.stopLoadingMessages();
    this.state = 'idle';
    this.currentY = PEACH_EMPTY_Y;
    this.targetY = PEACH_EMPTY_Y;
    this.waveAmplitude = 4;

    this.setOutlineDashed(true);
    this.hideCleanTick();

    if (this.bandEl) {
      this.bandEl.textContent = 'Idle';
      this.bandEl.className = 'meter-band';
      this.bandEl.style.opacity = '1';
    }
    if (this.explainerEl) {
      this.explainerEl.textContent = 'Paste text, HTML, or an image to measure manipulative pressure.';
    }

    if (this.svgBox) {
      this.svgBox.setAttribute('role', 'img');
      this.svgBox.setAttribute('aria-label', 'Peach empty, nothing detected');
      this.svgBox.removeAttribute('aria-valuenow');
      this.svgBox.removeAttribute('aria-valuemin');
      this.svgBox.removeAttribute('aria-valuemax');
    }
  }

  setAnalyzing() {
    this.stopPulse();
    this.state = 'analyzing';
    this.analyzePhase = 0;
    this.waveAmplitude = 9;

    this.setOutlineDashed(true);
    this.hideCleanTick();

    this.startLoadingMessages();

    if (this.a11yStatus) {
      this.a11yStatus.textContent = 'Analyzing input...';
    }
    if (this.svgBox) {
      this.svgBox.setAttribute('role', 'img');
      this.svgBox.setAttribute('aria-label', 'Peach meter: Analyzing');
    }
  }

  setResult(apiResult) {
    this.stopLoadingMessages();
    const summary = apiResult?.summary || {};

    if (summary.status === 'no_content') {
      this.setNoContent();
      return;
    }

    // Single rule for outcome: response.summary.flagged_items > 0
    const flagged = isFlagged(apiResult);
    const findings = apiResult?.findings || [];
    const flaggedCount = summary.flagged_items ?? findings.filter((f) => f.kind === 'flag').length;

    if (flagged) {
      this.setFlagged(flaggedCount);
    } else {
      this.setClean(apiResult);
    }
  }

  setFlagged(flaggedCount) {
    this.stopPulse();
    this.state = 'flagged';
    this.hideCleanTick();
    this.setOutlineSolid();

    // Side text fades in over ~300ms
    if (this.bandEl) {
      this.bandEl.textContent = 'Soft spots detected';
      this.bandEl.className = 'meter-band';
      this.bandEl.style.opacity = '0';
      requestAnimationFrame(() => {
        this.bandEl.style.transition = 'opacity 300ms ease';
        this.bandEl.style.opacity = '1';
      });
    }
    if (this.explainerEl) {
      this.explainerEl.textContent = 'Review each finding below.';
    }

    // Accessibility updates immediately
    if (this.svgBox) {
      this.svgBox.setAttribute('role', 'img');
      this.svgBox.setAttribute('aria-label', 'Peach full, soft spots detected');
      this.svgBox.removeAttribute('aria-valuenow');
      this.svgBox.removeAttribute('aria-valuemin');
      this.svgBox.removeAttribute('aria-valuemax');
    }
    if (this.a11yStatus) {
      const itemsWord = flaggedCount === 1 ? 'item' : 'items';
      this.a11yStatus.textContent = `Audit complete. Soft spots detected. ${flaggedCount} ${itemsWord} flagged.`;
    }

    if (prefersReducedMotion()) {
      this.renderReducedMotion();
      return;
    }

    // Start fill animation from current level to full over 3.2s
    this.fillStartTime = performance.now();
    this.fillStartY = this.currentY;
    this.waveAmplitudeStart = Math.max(6, this.waveAmplitude);
    this.isFilling = true;
  }

  setClean(apiResult) {
    this.stopPulse();
    this.state = 'clean';
    this.setOutlineSolid();

    if (this.bandEl) {
      this.bandEl.textContent = 'Fresh';
      this.bandEl.className = 'meter-band';
      this.bandEl.style.opacity = '0';
      requestAnimationFrame(() => {
        this.bandEl.style.transition = 'opacity 300ms ease';
        this.bandEl.style.opacity = '1';
      });
    }
    if (this.explainerEl) {
      this.explainerEl.textContent = 'No manipulative patterns detected. This does not guarantee a fair checkout.';
    }

    // Accessibility
    if (this.svgBox) {
      this.svgBox.setAttribute('role', 'img');
      this.svgBox.setAttribute('aria-label', 'Peach empty, nothing detected');
      this.svgBox.removeAttribute('aria-valuenow');
      this.svgBox.removeAttribute('aria-valuemin');
      this.svgBox.removeAttribute('aria-valuemax');
    }
    if (this.a11yStatus) {
      this.a11yStatus.textContent = 'Audit complete. Fresh. No items flagged.';
    }

    if (prefersReducedMotion()) {
      this.currentY = PEACH_EMPTY_Y;
      this.showCleanTick();
      this.renderReducedMotion();
      return;
    }

    // Drain fluid to empty over ~0.8s if not already empty
    if (this.currentY < PEACH_EMPTY_Y - 5) {
      this.drainStartTime = performance.now();
      this.drainStartY = this.currentY;
      this.isDraining = true;
      this.hideCleanTick();
    } else {
      this.currentY = PEACH_EMPTY_Y;
      this.isDraining = false;
      this.showCleanTick();
    }
  }

  setNoContent() {
    this.stopPulse();
    this.stopLoadingMessages();
    this.state = 'idle';
    this.currentY = PEACH_EMPTY_Y;
    this.waveAmplitude = 4;

    this.setOutlineDashed(true);
    this.hideCleanTick();

    if (this.bandEl) {
      this.bandEl.textContent = 'Idle';
      this.bandEl.className = 'meter-band';
      this.bandEl.style.opacity = '1';
    }
    if (this.explainerEl) {
      this.explainerEl.textContent = 'Nothing to read yet';
    }

    if (this.svgBox) {
      this.svgBox.setAttribute('role', 'img');
      this.svgBox.setAttribute('aria-label', 'Peach empty, nothing detected');
    }
    if (this.a11yStatus) {
      this.a11yStatus.textContent = 'Audit complete. Nothing to read yet.';
    }
  }

  setError(err) {
    this.stopPulse();
    this.stopLoadingMessages();
    this.state = 'error';
    this.currentY = PEACH_EMPTY_Y;
    this.waveAmplitude = 4;

    this.setOutlineDashed(true);
    this.hideCleanTick();

    if (this.bandEl) {
      this.bandEl.textContent = 'Error';
      this.bandEl.className = 'meter-band error-band';
      this.bandEl.style.opacity = '1';
    }
    if (this.explainerEl) {
      this.explainerEl.textContent = err?.message || 'Something went wrong. Check the server connection.';
    }

    this.pulseOutlineError();

    if (this.svgBox) {
      this.svgBox.setAttribute('role', 'img');
      this.svgBox.setAttribute('aria-label', 'Peach meter: Error');
    }
  }

  // =====================================================================
  // Visual Helpers
  // =====================================================================
  setOutlineDashed(dashed) {
    if (!this.peachOutline) return;
    if (dashed) {
      this.peachOutline.setAttribute('stroke-dasharray', '6 5');
      this.peachOutline.setAttribute('stroke', '#FF8A3D');
    }
  }

  setOutlineSolid() {
    if (!this.peachOutline) return;
    this.peachOutline.removeAttribute('stroke-dasharray');
    this.peachOutline.setAttribute('stroke', '#FF8A3D');
  }

  pulseOutlineError() {
    if (!this.peachOutline) return;
    this.peachOutline.setAttribute('stroke', '#FF4D1C');
    let pulses = 0;
    const interval = setInterval(() => {
      pulses++;
      this.peachOutline.setAttribute('opacity', pulses % 2 === 0 ? '1' : '0.4');
      if (pulses >= 6) {
        clearInterval(interval);
        this.peachOutline.setAttribute('opacity', '1');
        this.peachOutline.setAttribute('stroke', '#FF8A3D');
      }
    }, 300);
  }

  showCleanTick() {
    if (!this.cleanTick) return;
    if (prefersReducedMotion()) {
      this.cleanTick.setAttribute('opacity', '1');
      return;
    }
    let op = 0;
    const fade = () => {
      op += 0.05;
      if (op >= 1) {
        this.cleanTick.setAttribute('opacity', '1');
        return;
      }
      this.cleanTick.setAttribute('opacity', String(op.toFixed(2)));
      requestAnimationFrame(fade);
    };
    requestAnimationFrame(fade);
  }

  hideCleanTick() {
    if (this.cleanTick) {
      this.cleanTick.setAttribute('opacity', '0');
    }
  }

  wobble() {
    if (!this.svgBox) return;
    this.svgBox.classList.remove('wobble');
    void this.svgBox.offsetWidth;
    this.svgBox.classList.add('wobble');
    this.svgBox.addEventListener('animationend', () => {
      this.svgBox.classList.remove('wobble');
    }, { once: true });
  }

  // =====================================================================
  // Loading Messages Rotation
  // =====================================================================
  startLoadingMessages() {
    this.loadingMsgIndex = 0;
    this.showLoadingMessage();
    this.loadingMsgTimer = setInterval(() => {
      this.loadingMsgIndex = (this.loadingMsgIndex + 1) % LOADING_MESSAGES.length;
      this.showLoadingMessage();
    }, 2200);
  }

  showLoadingMessage() {
    if (this.bandEl) {
      this.bandEl.className = 'meter-band loading-msg';
      this.bandEl.textContent = LOADING_MESSAGES[this.loadingMsgIndex];
      this.bandEl.style.opacity = '1';
    }
    if (this.explainerEl) {
      this.explainerEl.textContent = '';
    }
  }

  stopLoadingMessages() {
    if (this.loadingMsgTimer) {
      clearInterval(this.loadingMsgTimer);
      this.loadingMsgTimer = null;
    }
  }

  // =====================================================================
  // Cleanup
  // =====================================================================
  destroy() {
    this.stop();
    this.stopPulse();
    this.stopLoadingMessages();
  }
}
