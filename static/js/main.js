/**
 * CheekShield AI — Main Client Entry (Phases 1-4)
 */

import { PeachField } from './peachfield.js';
import { store } from './state.js';
import { fetchHealth, fetchModelInfo } from './api.js';
import { InputController } from './input.js';
import { MeterController } from './meter.js';
import { TallyController } from './tally.js';
import { FindingsController } from './findings.js';
import { ScreenshotViewer } from './viewer.js';
import { ExportController } from './export.js';

let peachField = null;
let inputController = null;
let meterController = null;
let tallyController = null;
let findingsController = null;
let viewerController = null;
let exportController = null;

document.addEventListener('DOMContentLoaded', async () => {
  // 1. Initialize Peach Field Canvas (Phase 1)
  const canvas = document.getElementById('peachfield');
  if (canvas) {
    peachField = new PeachField(canvas);
  }

  // 2. Initialize Input Controller (Phase 2)
  inputController = new InputController();

  // 3. Initialize Peach Meter Controller (Phase 3)
  meterController = new MeterController();

  // 4. Initialize Results Controllers (Phase 4)
  tallyController = new TallyController();
  exportController = new ExportController();

  // Cross-wire Screenshot Viewer and Findings List for synchronized highlights
  viewerController = new ScreenshotViewer({
    onBoxHover: (id) => findingsController?.highlightFindingRow(id),
    onBoxLeave: () => findingsController?.clearFindingRowHighlight(),
    onBoxClick: (id) => findingsController?.highlightFindingRow(id, true),
  });

  findingsController = new FindingsController({
    onRowHover: (id) => viewerController?.highlightBox(id),
    onRowLeave: () => viewerController?.clearBoxHighlight(),
    onShowOnScreenshot: (id) => viewerController?.focusBox(id),
  });

  // 5. Listen to audit events
  window.addEventListener('cheek:audit-start', () => {
    if (peachField) peachField.setAuditing(true);
  });

  const onAuditEnd = () => {
    if (peachField) peachField.setAuditing(false);
  };
  window.addEventListener('cheek:audit-cancel', onAuditEnd);
  window.addEventListener('cheek:audit-error', onAuditEnd);

  function renderResult(result) {
    if (!result) return;

    // Render results into meter, tally, findings, and viewer
    meterController?.setResult(result);
    tallyController?.render(result);
    findingsController?.render(result);
    viewerController?.render(result);

    // Mobile UX (Section 6.5): scroll meter into view after audit
    if (window.innerWidth < 760) {
      const meterEl = document.getElementById('meter-card');
      if (meterEl) {
        meterEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  }

  window.addEventListener('cheek:audit-success', (e) => {
    onAuditEnd();
    renderResult(e.detail);
  });

  // 6. Health check & Status Chip
  await initHealth();

  // 7. Load model info
  await initModelInfo();

  // 8. Demo Sequence & Shortcut (Section 7 Phase 7 point 6, Section 12)
  initDemoMode();

  // 9. Auto-run if query param present (?auto=deceptive | ?auto=clean)
  const urlParams = new URLSearchParams(window.location.search);
  const auto = urlParams.get('auto');
  if (auto === 'deceptive') {
    setTimeout(() => {
      document.getElementById('sample-deceptive-btn')?.click();
      setTimeout(() => {
        document.getElementById('btn-audit')?.click();
        setTimeout(() => {
          const firstFix = document.querySelector('.fix-disclosure');
          if (firstFix) firstFix.open = true;
        }, 800);
      }, 300);
    }, 400);
  } else if (auto === 'clean') {
    setTimeout(() => {
      document.getElementById('sample-clean-btn')?.click();
      setTimeout(() => {
        document.getElementById('btn-audit')?.click();
      }, 300);
    }, 400);
  }
});

async function initHealth() {
  const chip = document.getElementById('model-status-chip');
  const text = document.getElementById('model-status-text');

  try {
    const health = await fetchHealth();
    chip.className = `status-chip ${health.status}`;
    store.set({
      modelReady: health.status === 'ready',
      modelStatus: health.status,
      ocrReady: Boolean(health.ocr_ready),
      engine: health.engine,
      demoReplay: Boolean(health.demo_replay),
    });

    if (health.status === 'ready') {
      if (health.engine === 'mock') {
        text.textContent = 'Mock engine';
        chip.title = 'Mock engine is active (CHEEK_MOCK=1).';
      } else {
        text.textContent = 'Model ready';
        chip.title = 'Model is loaded and ready for audits.';
      }
    } else if (health.status === 'warming') {
      text.textContent = 'Warming up';
      chip.title = health.message || 'Model is warming up, the first audit can take longer.';
      // Poll once after 2 seconds
      setTimeout(initHealth, 2000);
    } else if (health.status === 'model_missing') {
      text.textContent = 'Model missing';
      const msg = health.message || 'The model is not loaded. Put the trained model in outputs/model/ (it must contain meta.json) and restart the server.';
      chip.title = msg;
      meterController?.setError({ message: msg });
    } else {
      text.textContent = 'Model error';
      chip.title = health.message || 'Engine encountered an error.';
    }
  } catch (err) {
    chip.className = 'status-chip error';
    text.textContent = 'Server offline';
    chip.title = 'Cannot reach backend server.';
    store.set({ modelReady: false, modelStatus: 'error' });
  }
}

// =============================================================================
// Demo Runner (Section 7 Phase 7 point 6, Section 12)
// =============================================================================
function initDemoMode() {
  const urlParams = new URLSearchParams(window.location.search);
  const isDemo = urlParams.get('demo') === '1' || urlParams.has('demo');

  // Global keyboard shortcut: Alt+D or Ctrl+Shift+D
  window.addEventListener('keydown', (e) => {
    if ((e.altKey && (e.key === 'd' || e.key === 'D')) ||
        (e.ctrlKey && e.shiftKey && (e.key === 'd' || e.key === 'D'))) {
      e.preventDefault();
      toggleDemoToolbar();
    }
  });

  if (isDemo) {
    toggleDemoToolbar(true);
    // Auto-run Step 1 of demo script
    setTimeout(() => runDemoStep(1), 500);
  }
}

let demoToolbarEl = null;

function toggleDemoToolbar(forceOpen = null) {
  if (!demoToolbarEl) {
    demoToolbarEl = document.createElement('div');
    demoToolbarEl.className = 'demo-toolbar';
    demoToolbarEl.setAttribute('role', 'region');
    demoToolbarEl.setAttribute('aria-label', 'Demo controls');
    demoToolbarEl.innerHTML = `
      <span class="demo-toolbar-label">Demo:</span>
      <button type="button" class="demo-step-btn" data-step="1" title="1. Deceptive sample audit">1. Deceptive</button>
      <button type="button" class="demo-step-btn" data-step="2" title="2. Inspect findings & ethical fix">2. Fix</button>
      <button type="button" class="demo-step-btn" data-step="3" title="3. Screenshot viewer">3. Screen</button>
      <button type="button" class="demo-step-btn" data-step="4" title="4. Clean sample (Fresh)">4. Clean</button>
      <button type="button" class="demo-step-btn" data-step="5" title="5. Inspect model evaluation panel">5. Model</button>
      <button type="button" class="demo-step-btn" data-step="6" title="6. Save PDF export">6. Export</button>
    `;
    demoToolbarEl.addEventListener('click', (e) => {
      const btn = e.target.closest('.demo-step-btn');
      if (btn) {
        const step = parseInt(btn.dataset.step, 10);
        runDemoStep(step);
      }
    });
    document.body.appendChild(demoToolbarEl);
  }

  if (forceOpen === true) {
    demoToolbarEl.hidden = false;
  } else if (forceOpen === false) {
    demoToolbarEl.hidden = true;
  } else {
    demoToolbarEl.hidden = !demoToolbarEl.hidden;
  }
}

function runDemoStep(step) {
  switch (step) {
    case 1: // Deceptive sample audit
      document.getElementById('tab-text')?.click();
      setTimeout(() => {
        document.getElementById('sample-deceptive-btn')?.click();
        setTimeout(() => {
          document.getElementById('btn-audit')?.click();
        }, 200);
      }, 100);
      break;

    case 2: // Inspect first finding & open ethical fix
      {
        const fix = document.querySelector('.fix-disclosure');
        if (fix) {
          fix.open = true;
          fix.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }
      break;

    case 3: // Switch to screenshot tab & run
      document.getElementById('tab-screenshot')?.click();
      setTimeout(() => {
        document.getElementById('sample-deceptive-btn')?.click();
        setTimeout(() => {
          document.getElementById('btn-audit')?.click();
        }, 300);
      }, 150);
      break;

    case 4: // Clean sample & Fresh state
      document.getElementById('tab-text')?.click();
      setTimeout(() => {
        document.getElementById('sample-clean-btn')?.click();
        setTimeout(() => {
          document.getElementById('btn-audit')?.click();
        }, 200);
      }, 100);
      break;

    case 5: // Model evaluation panel
      document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' });
      break;

    case 6: // Export
      document.getElementById('receipt-strip')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      break;
  }
}

function formatThreshold(val) {
  if (val == null || val === '' || isNaN(Number(val))) {
    return '—';
  }
  return Number(val).toFixed(2);
}

async function initModelInfo() {
  try {
    const info = await fetchModelInfo();
    if (!info) return;

    // Macro F1
    const macroEl = document.getElementById('metric-macro-f1');
    if (macroEl && info.macro_f1 != null) {
      macroEl.textContent = `${(info.macro_f1 * 100).toFixed(1)}%`;
    }

    // Binary metrics (Precision, Recall, F1, Threshold)
    if (info.binary) {
      const precEl = document.getElementById('metric-binary-precision');
      const recEl = document.getElementById('metric-binary-recall');
      const f1El = document.getElementById('metric-binary-f1');
      const threshEl = document.getElementById('metric-dark-threshold');
      if (precEl && info.binary.precision != null) precEl.textContent = `${(info.binary.precision * 100).toFixed(1)}%`;
      if (recEl && info.binary.recall != null) recEl.textContent = `${(info.binary.recall * 100).toFixed(1)}%`;
      if (f1El) {
        const f1Val = info.binary.f1 != null ? info.binary.f1 : info.binary['f1-score'];
        if (f1Val != null) f1El.textContent = `${(f1Val * 100).toFixed(1)}%`;
      }
      if (threshEl) {
        const rawThresh = info.binary?.threshold ?? info.dark_threshold;
        threshEl.textContent = formatThreshold(rawThresh);
      }
    }

    // Model names & tags
    const modelBadge = document.getElementById('model-chip-badge');
    if (modelBadge && info.name) {
      modelBadge.textContent = `${info.name} Base Uncased`;
    }
    const footerModel = document.getElementById('footer-model-version');
    if (footerModel && info.name) {
      footerModel.textContent = `Model: ${info.name} (${info.dir_label || 'outputs/model'})`;
    }

    // Temperature
    const tempEl = document.getElementById('meta-temp');
    if (tempEl && info.temperature) {
      tempEl.textContent = `T = ${info.temperature}`;
    }

    // Populate Per-Class Table
    const tbody = document.getElementById('per-class-tbody');
    if (tbody && info.per_class) {
      tbody.innerHTML = '';
      for (const [cls, stats] of Object.entries(info.per_class)) {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td style="text-align: left; font-weight: 500;">${cls}</td>
          <td>${(stats.precision * 100).toFixed(1)}%</td>
          <td>${(stats.recall * 100).toFixed(1)}%</td>
          <td>${(stats.f1 * 100).toFixed(1)}%</td>
          <td>${stats.support}</td>
        `;
        tbody.appendChild(row);
      }
    }

    // Populate Confusion Matrix Heatmap
    const matrixBox = document.getElementById('confusion-matrix-box');
    if (matrixBox && info.confusion_matrix && info.classes) {
      const classes = info.classes;
      const matrix = info.confusion_matrix;
      let html = '<table class="matrix-table"><thead><tr><th style="text-align:left;">True \\ Pred</th>';
      for (const cls of classes) {
        html += `<th>${cls}</th>`;
      }
      html += '</tr></thead><tbody>';

      for (let r = 0; r < matrix.length; r++) {
        const rowTotal = matrix[r].reduce((a, b) => a + b, 0) || 1;
        html += `<tr><td style="text-align:left; font-weight:600; background:var(--ink-2);">${classes[r] || r}</td>`;
        for (let c = 0; c < matrix[r].length; c++) {
          const val = matrix[r][c];
          const pct = val / rowTotal;
          // Orange intensity based on row percentage
          const alpha = (pct * 0.7).toFixed(2);
          html += `<td class="matrix-cell" style="background: rgba(255, 138, 61, ${alpha});">${val}</td>`;
        }
        html += '</tr>';
      }
      html += '</tbody></table>';
      matrixBox.innerHTML = html;
    }
  } catch (err) {
    console.warn('Could not load model info:', err);
  }
}
