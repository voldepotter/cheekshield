/**
 * CheekShield AI — Cheekometer Controller (Section 7 Phase 3)
 *
 * States: idle, analyzing, result, clean, error
 *
 * The SVG peach is already in index.html. This module drives:
 *  - Fluid wave animation (two sinusoidal paths clipped to peach shape)
 *  - Spring physics for fluid level with overshoot
 *  - Juice streaks and bubbles inside the fluid
 *  - Number count-up animation (easeOutCubic)
 *  - Band label fade-in
 *  - ARIA meter updates & live region announcements
 *  - Easter egg wobble on click
 *  - Calculation popover toggle
 *  - Loading message rotation
 *  - Reduced motion support
 */

const LOADING_MESSAGES = [
  'Cheeko is reading the page',
  'Looking for pressure words',
  'Checking buttons and boxes',
  'Weighing the evidence',
];

// SVG coordinate system: viewBox 0 0 240 280
// Peach body spans roughly Y=44 (top dip) to Y=252 (bottom)
const PEACH_TOP = 44;
const PEACH_BOTTOM = 252;
const PEACH_RANGE = PEACH_BOTTOM - PEACH_TOP; // 208

// Convert percent (0-100) to Y coordinate in SVG space
function percentToY(pct) {
  // 0% → bottom (252), 100% → top (44)
  return PEACH_BOTTOM - (pct / 100) * PEACH_RANGE;
}

// easeOutCubic for count-up
function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

// Check reduced motion preference
function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export class MeterController {
  constructor() {
    // DOM elements
    this.svgBox = document.getElementById('meter-svg-box');
    this.waveFront = document.getElementById('meter-wave-front');
    this.waveBack = document.getElementById('meter-wave-back');
    this.fluidGroup = document.getElementById('meter-fluid-group');
    this.peachOutline = document.getElementById('meter-peach-outline');
    this.cleanTick = document.getElementById('meter-clean-tick');
    this.numberEl = document.getElementById('meter-number');
    this.percentSign = document.getElementById('meter-percent-sign');
    this.bandEl = document.getElementById('meter-band');
    this.explainerEl = document.getElementById('meter-explainer');
    this.calcToggle = document.getElementById('meter-calc-toggle');
    this.calcPopover = document.getElementById('calc-popover');
    this.a11yStatus = document.getElementById('a11y-status');

    // State
    this.state = 'idle'; // idle | analyzing | result | clean | error
    this.targetPercent = 0;
    this.currentLevel = 0; // current Y percent (0-100), animated
    this.velocity = 0; // spring velocity
    this.displayNumber = 0; // currently displayed integer
    this.targetNumber = 0;

    // Wave parameters
    this.wavePhase = 0;
    this.waveAmplitude = 6; // base amplitude
    this.waveAmplitudeTarget = 6;
    this.sloshing = false;
    this.sloshDecay = 0;

    // Idle bob
    this.bobPhase = 0;

    // Loading message rotation
    this.loadingMsgIndex = 0;
    this.loadingMsgTimer = null;

    // Analyzing slosh range
    this.analyzePhase = 0;

    // Count-up animation
    this.countStartTime = 0;
    this.countDuration = 1200; // 1.2s
    this.countFrom = 0;
    this.countTo = 0;
    this.isCounting = false;

    // Animation frame
    this.animFrame = null;
    this.lastTime = 0;
    this.running = false;

    // Bubbles
    this.bubbles = [];
    this.streaks = [];

    this.init();
  }

  init() {
    // Easter egg: wobble on click
    if (this.svgBox) {
      this.svgBox.addEventListener('click', () => this.wobble());
    }

    // Calculation popover toggle
    if (this.calcToggle && this.calcPopover) {
      this.calcToggle.addEventListener('click', () => {
        const expanded = this.calcToggle.getAttribute('aria-expanded') === 'true';
        this.calcToggle.setAttribute('aria-expanded', String(!expanded));
        this.calcPopover.hidden = expanded;
      });
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

    // Initialize streaks (static decorative lines inside the fluid)
    this.initStreaks();
    // Initialize bubbles pool
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

    let elapsed = Math.min(Math.max(0, (now - this.lastTime) / 1000), 2.0); // max catch-up 2s
    this.lastTime = now;

    if (prefersReducedMotion()) {
      // Static render, no animation
      this.currentLevel = this.targetPercent;
      this.displayNumber = this.targetNumber;
      this.renderWaves(0);
      this.renderNumber();
    } else {
      // Fixed-timestep physics simulation for frame-rate independence
      const step = 1 / 60;
      while (elapsed > 0) {
        const subDt = Math.min(elapsed, step);
        this.updatePhysics(subDt);
        this.updateBubbles(subDt);
        elapsed -= subDt;
      }

      const dt = Math.min((now - this.lastTime) / 1000, 0.05);
      this.wavePhase += (now / 1000) * 2.2;
      this.bobPhase = now / 1000;
      this.renderWaves(dt);
      this.updateCountUp();
      this.renderNumber();
    }

    this.animFrame = requestAnimationFrame((t) => this.tick(t));
  }

  // =====================================================================
  // Spring Physics — fluid level eases to target with slight overshoot
  // =====================================================================
  updatePhysics(dt) {
    if (this.state === 'analyzing') {
      // Indeterminate slosh between ~15% and ~35%
      this.analyzePhase += dt * 1.3;
      this.targetPercent = 25 + 10 * Math.sin(this.analyzePhase);
    }

    // Spring: stiffness and damping (snappy fill ~600ms with slight overshoot)
    const stiffness = 28.0;
    const damping = 6.5;
    const diff = this.targetPercent - this.currentLevel;
    const springForce = diff * stiffness;
    const dampForce = -this.velocity * damping;
    this.velocity += (springForce + dampForce) * dt;
    this.currentLevel += this.velocity * dt;

    // Decay slosh amplitude
    if (this.sloshing) {
      this.sloshDecay -= dt;
      if (this.sloshDecay <= 0) {
        this.sloshing = false;
        this.waveAmplitudeTarget = 6;
      }
      // Lerp amplitude back
      this.waveAmplitude += (this.waveAmplitudeTarget - this.waveAmplitude) * dt * 2;
    }
  }

  // =====================================================================
  // Wave Rendering — two sinusoidal paths
  // =====================================================================
  renderWaves(dt) {
    const level = percentToY(Math.max(0, Math.min(100, this.currentLevel)));

    // Add gentle bob in idle/clean states
    let bob = 0;
    if (this.state === 'idle' || this.state === 'clean' || this.state === 'error') {
      bob = Math.sin(this.bobPhase * Math.PI / 2) * 3; // ~3px, ~4s period
    }

    const y = level + bob;
    const amp = this.waveAmplitude;

    // Build wave path for the front wave
    const frontPath = this.buildWavePath(y, amp, this.wavePhase, 0.04);
    // Build wave path for the back wave (different phase, slightly larger amplitude)
    const backPath = this.buildWavePath(y + 3, amp * 0.7, this.wavePhase + 2.0, 0.035);

    if (this.waveFront) this.waveFront.setAttribute('d', frontPath);
    if (this.waveBack) this.waveBack.setAttribute('d', backPath);

    // Render streaks inside fluid
    this.renderStreaks(y);
    // Render bubbles
    this.renderBubblesDOM(y);
  }

  buildWavePath(baseY, amplitude, phase, frequency) {
    const width = 240;
    const segments = 24;
    const step = width / segments;

    let d = `M 0 ${baseY}`;
    for (let i = 0; i <= segments; i++) {
      const x = i * step;
      const waveY = baseY + amplitude * Math.sin(frequency * x * 10 + phase);
      d += ` L ${x.toFixed(1)} ${waveY.toFixed(1)}`;
    }
    // Close at bottom
    d += ` L 240 280 L 0 280 Z`;
    return d;
  }

  // =====================================================================
  // Juice Streaks — subtle vertical lines inside the fluid
  // =====================================================================
  initStreaks() {
    this.streaks = [];
    // Create streak elements in the SVG fluid group
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
      if (height < 5 || fluidTop > 260) {
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

  // =====================================================================
  // Bubbles — small circles that rise and pop inside the fluid
  // =====================================================================
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
    const fluidTop = percentToY(Math.max(0, Math.min(100, this.currentLevel)));
    const hasFluid = this.currentLevel > 2;

    for (const b of this.bubbles) {
      if (!b.alive) {
        // Spawn with low probability when there's fluid
        if (hasFluid && Math.random() < dt * 0.8) {
          b.alive = true;
          b.x = 40 + Math.random() * 160;
          b.y = PEACH_BOTTOM - 10;
          b.r = 1.5 + Math.random() * 2;
          b.speed = 20 + Math.random() * 25;
          b.life = 0;
          b.el.setAttribute('r', b.r);
        }
        continue;
      }

      b.y -= b.speed * dt;
      b.x += Math.sin(b.life * 4) * 8 * dt; // gentle sideways drift
      b.life += dt;

      // Pop when reaching near the surface or too old
      if (b.y < fluidTop + 5 || b.life > 4) {
        b.alive = false;
        b.el.setAttribute('opacity', '0');
        continue;
      }

      b.el.setAttribute('cx', b.x.toFixed(1));
      b.el.setAttribute('cy', b.y.toFixed(1));
      // Fade as approaching surface
      const distToSurface = b.y - fluidTop;
      const alpha = Math.min(0.3, distToSurface / 60);
      b.el.setAttribute('opacity', alpha.toFixed(2));
    }
  }

  renderBubblesDOM(fluidTop) {
    // Already updated in updateBubbles, this is a no-op placeholder
  }

  // =====================================================================
  // Count-Up Animation
  // =====================================================================
  startCountUp(from, to) {
    this.countFrom = typeof from === 'number' && !isNaN(from) ? Math.max(0, from) : 0;
    this.countTo = typeof to === 'number' && !isNaN(to) ? Math.max(0, to) : 0;
    this.countStartTime = performance.now();
    this.isCounting = true;
  }

  updateCountUp() {
    if (!this.isCounting) return;

    const currentTime = performance.now();
    const elapsed = Math.max(0, currentTime - this.countStartTime);
    const progress = Math.min(Math.max(0, elapsed / this.countDuration), 1);
    const eased = easeOutCubic(progress);

    this.displayNumber = Math.round(this.countFrom + (this.countTo - this.countFrom) * eased);

    if (progress >= 1) {
      this.displayNumber = this.countTo;
      this.isCounting = false;
    }
  }

  renderNumber() {
    if (!this.numberEl) return;

    if (this.state === 'analyzing') {
      // Already set via loading message timer
      return;
    }

    if (this.state === 'idle' || this.state === 'error') {
      // en dash already set in setState
      return;
    }

    if (this.state === 'clean') {
      this.numberEl.textContent = '0';
      return;
    }

    // Result or clean: show the number
    this.numberEl.textContent = String(this.displayNumber);
  }

  // =====================================================================
  // State Transitions
  // =====================================================================
  setIdle() {
    this.state = 'idle';
    this.targetPercent = 0;
    this.targetNumber = 0;
    this.displayNumber = 0;
    this.countFrom = 0;
    this.countTo = 0;
    this.isCounting = false;
    this.velocity = 0;
    this.waveAmplitude = 6;
    this.waveAmplitudeTarget = 6;
    this.stopLoadingMessages();

    // Visuals
    this.setOutlineDashed(true);
    this.hideCleanTick();
    if (this.numberEl) this.numberEl.textContent = '\u2013'; // en dash
    if (this.percentSign) this.percentSign.hidden = true;
    if (this.bandEl) this.bandEl.textContent = 'Idle';
    if (this.explainerEl) this.explainerEl.textContent = 'Paste text, HTML, or an image to measure manipulative pressure.';

    // ARIA
    this.updateAria(0, 'Idle');
  }

  setAnalyzing() {
    this.state = 'analyzing';
    this.analyzePhase = 0;
    this.velocity = 0;
    this.waveAmplitude = 10;
    this.waveAmplitudeTarget = 10;

    // Visuals
    this.setOutlineDashed(true);
    this.hideCleanTick();
    if (this.percentSign) this.percentSign.hidden = true;
    if (this.bandEl) this.bandEl.textContent = '';

    // Start loading message rotation
    this.startLoadingMessages();

    // ARIA
    if (this.a11yStatus) this.a11yStatus.textContent = 'Analyzing input...';
    if (this.svgBox) {
      this.svgBox.setAttribute('aria-label', 'Cheekometer: Analyzing');
    }
  }

  setResult(apiResult) {
    this.stopLoadingMessages();
    const summary = apiResult?.summary || {};
    if (summary.status === 'no_content') {
      this.setNoContent();
      return;
    }

    const exposure = apiResult?.exposure || apiResult?.summary?.exposure || {};
    const percent = exposure.percent ?? 0;
    const band = exposure.label || 'Fresh';
    const findings = apiResult?.findings || [];
    const flaggedCount = findings.filter(f => f.kind === 'flag').length;

    if (percent === 0 || summary.status === 'clean') {
      // Clean result
      this.setClean(apiResult);
      return;
    }

    this.state = 'result';
    this.targetPercent = percent;
    this.targetNumber = percent;

    // Trigger slosh (wave amplitude spike)
    this.sloshing = true;
    this.sloshDecay = 2.0;
    this.waveAmplitude = 14 + Math.min(percent / 5, 10); // bigger slosh for higher result
    this.waveAmplitudeTarget = 6;

    // Count-up from current display
    this.startCountUp(this.displayNumber, percent);

    // Visuals
    this.setOutlineSolid();
    this.hideCleanTick();
    if (this.percentSign) this.percentSign.hidden = false;
    if (this.bandEl) {
      this.bandEl.textContent = band;
      this.bandEl.style.opacity = '0';
      // Fade in band label
      requestAnimationFrame(() => {
        this.bandEl.style.transition = 'opacity 0.5s ease';
        this.bandEl.style.opacity = '1';
      });
    }
    if (this.explainerEl) {
      this.explainerEl.textContent = this.getExplainerText(percent, band);
    }

    // ARIA
    this.updateAria(percent, band);
    if (this.a11yStatus) {
      this.a11yStatus.textContent = `Audit complete. ${percent} percent exposure. ${flaggedCount} ${flaggedCount === 1 ? 'item' : 'items'} flagged.`;
    }
  }

  setClean(apiResult) {
    this.state = 'clean';
    this.targetPercent = 0;
    this.targetNumber = 0;
    this.displayNumber = 0;
    this.countFrom = 0;
    this.countTo = 0;
    this.isCounting = false;
    this.velocity = 0;
    this.waveAmplitude = 4;
    this.waveAmplitudeTarget = 4;
    this.stopLoadingMessages();

    // Visuals
    this.setOutlineSolid();
    this.showCleanTick();
    if (this.numberEl) this.numberEl.textContent = '0';
    if (this.percentSign) this.percentSign.hidden = false;
    if (this.bandEl) this.bandEl.textContent = 'Fresh';
    if (this.explainerEl) this.explainerEl.textContent = 'No manipulative patterns detected. This does not guarantee a fair checkout.';

    // ARIA
    this.updateAria(0, 'Fresh');
    if (this.a11yStatus) {
      this.a11yStatus.textContent = 'Audit complete. 0 percent exposure. No dark patterns found. Fresh.';
    }
  }

  setNoContent() {
    this.state = 'idle';
    this.targetPercent = 0;
    this.targetNumber = 0;
    this.displayNumber = 0;
    this.countFrom = 0;
    this.countTo = 0;
    this.isCounting = false;
    this.velocity = 0;
    this.stopLoadingMessages();

    // Visuals: Idle look plus "Nothing to read yet" (Section 7 Phase 3, Section 10)
    this.setOutlineDashed(true);
    this.hideCleanTick();
    if (this.numberEl) this.numberEl.textContent = '\u2013'; // en dash
    if (this.percentSign) this.percentSign.hidden = true;
    if (this.bandEl) this.bandEl.textContent = 'Idle';
    if (this.explainerEl) {
      this.explainerEl.textContent = 'Nothing to read yet';
    }

    // ARIA
    this.updateAria(0, 'Nothing to read yet');
    if (this.a11yStatus) {
      this.a11yStatus.textContent = 'Audit complete. Nothing to read yet.';
    }
  }

  setError(err) {
    this.state = 'error';
    this.targetPercent = 0;
    this.targetNumber = 0;
    this.displayNumber = 0;
    this.countFrom = 0;
    this.countTo = 0;
    this.isCounting = false;
    this.velocity = 0;
    this.stopLoadingMessages();

    // Visuals
    this.setOutlineDashed(true);
    this.hideCleanTick();
    if (this.numberEl) this.numberEl.textContent = '\u2013'; // en dash
    if (this.percentSign) this.percentSign.hidden = true;
    if (this.bandEl) this.bandEl.textContent = 'Error';
    if (this.explainerEl) {
      const msg = err?.message || 'Something went wrong. Check the server connection.';
      this.explainerEl.textContent = msg;
    }

    // Pulse outline red briefly
    this.pulseOutlineError();

    // ARIA
    if (this.svgBox) {
      this.svgBox.setAttribute('aria-label', 'Cheekometer: Error');
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
    // Three pulses via opacity
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
    // Fade in
    let op = 0;
    const fade = () => {
      op += 0.04;
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
    // Force reflow
    void this.svgBox.offsetWidth;
    this.svgBox.classList.add('wobble');
    this.svgBox.addEventListener('animationend', () => {
      this.svgBox.classList.remove('wobble');
    }, { once: true });
  }

  // =====================================================================
  // Loading Messages (rotate max 4, cycle)
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
    if (this.numberEl) {
      // Show ellipsis animation text
      this.numberEl.textContent = '';
    }
    if (this.bandEl) {
      this.bandEl.textContent = LOADING_MESSAGES[this.loadingMsgIndex];
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
  // ARIA Updates
  // =====================================================================
  updateAria(percent, bandLabel) {
    if (!this.svgBox) return;
    this.svgBox.setAttribute('aria-valuenow', String(percent));
    this.svgBox.setAttribute('aria-label', `Cheekometer Exposure Level: ${percent} percent (${bandLabel})`);
  }

  // =====================================================================
  // Explainer Text
  // =====================================================================
  getExplainerText(percent, band) {
    if (percent === 0) return 'No manipulative patterns detected. This does not guarantee a fair checkout.';
    if (percent < 25) return 'A few minor pressure signals. Likely routine but worth reviewing.';
    if (percent < 50) return 'Several influence tactics detected. Review each finding.';
    if (percent < 75) return 'Significant manipulative pressure. Users may be misled.';
    return 'High dark-pattern density. This interface appears heavily manipulative.';
  }

  // =====================================================================
  // Cleanup
  // =====================================================================
  destroy() {
    this.stop();
    this.stopLoadingMessages();
  }
}
