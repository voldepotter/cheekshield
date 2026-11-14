/**
 * CheekShield AI — Receipt Tally Controller (Section 6.7, Section 7 Phase 4)
 *
 * Populates the white paper receipt strip with:
 *  - Every category from the registry (plus unknown categories found in input)
 *  - Item counts and highest risk tier
 *  - Summary metrics: flagged, checked, routine, highest risk, mode, elapsed time, exposure %
 *  - Print-out stepped animation
 */

import { getAllDisplayCategories } from './categories.js';

export class TallyController {
  constructor() {
    this.stripEl = document.getElementById('receipt-strip');
    this.categoryRowsEl = document.getElementById('receipt-category-rows');
    this.flaggedCountEl = document.getElementById('receipt-flagged-count');
    this.checkedCountEl = document.getElementById('receipt-checked-count');
    this.routineCountEl = document.getElementById('receipt-routine-count');
    this.highestRiskEl = document.getElementById('receipt-highest-risk');
    this.inputModeEl = document.getElementById('receipt-input-mode');
    this.elapsedTimeEl = document.getElementById('receipt-elapsed-time');
  }

  /**
   * Render audit results into the receipt strip.
   * @param {Object} result - Normalized API v1 response
   */
  render(result) {
    if (!result) return;

    const findings = result.findings || [];
    const summary = result.summary || {};

    // 1. Collect unique categories from flagged findings (excluding benign 'Not Dark Pattern')
    const findingCategories = findings
      .filter((f) => f.kind === 'flag' && f.category && f.category.toLowerCase() !== 'not dark pattern')
      .map((f) => f.category);
    const displayCategories = getAllDisplayCategories(findingCategories)
      .filter((c) => c.name.toLowerCase() !== 'not dark pattern');

    // 2. Map flagged findings by category
    const flaggedByCategory = new Map();
    for (const f of findings) {
      if (f.kind === 'flag' && f.category && f.category.toLowerCase() !== 'not dark pattern') {
        const catKey = f.category.toLowerCase();
        if (!flaggedByCategory.has(catKey)) {
          flaggedByCategory.set(catKey, []);
        }
        flaggedByCategory.get(catKey).push(f);
      }
    }

    // 3. Build category rows
    if (this.categoryRowsEl) {
      this.categoryRowsEl.innerHTML = '';

      for (const cat of displayCategories) {
        const catKey = cat.name.toLowerCase();
        const flags = flaggedByCategory.get(catKey) || [];
        const count = flags.length;

        const row = document.createElement('div');
        row.className = 'receipt-row';

        if (count === 0) {
          row.classList.add('dimmed');
          row.innerHTML = `
            <span class="col-item">${this.escapeHtml(cat.name)}</span>
            <span class="leader" aria-hidden="true"></span>
            <span class="col-qty">0</span>
            <span class="col-risk">–</span>
          `;
        } else {
          // Find highest risk rank
          let highestRank = 1;
          let highestLabel = 'Low';
          for (const f of flags) {
            const rank = f.risk_rank || 1;
            if (rank > highestRank) {
              highestRank = rank;
              highestLabel = rank === 3 ? 'High' : rank === 2 ? 'Medium' : 'Low';
            }
          }

          const notchesHtml = this.renderNotches(highestRank);
          row.classList.add('non-zero');
          row.innerHTML = `
            <span class="col-item"><span class="receipt-pip" aria-hidden="true"></span>${this.escapeHtml(cat.name)}</span>
            <span class="leader" aria-hidden="true"></span>
            <span class="col-qty">${count}</span>
            <span class="col-risk">${notchesHtml}<span class="sr-only">${highestLabel} risk</span></span>
          `;
        }

        this.categoryRowsEl.appendChild(row);
      }
    }

    // 4. Update summary counts
    const flaggedCount = summary.flagged_items ?? findings.filter((f) => f.kind === 'flag').length;
    const checkedCount = summary.checked_fine ?? findings.filter((f) => f.kind === 'checked').length;
    const routineCount = summary.routine_preselections ?? findings.filter((f) => f.kind === 'routine_preselection').length;

    if (this.flaggedCountEl) {
      this.flaggedCountEl.textContent = String(flaggedCount);
      if (flaggedCount > 0) {
        this.flaggedCountEl.style.fontWeight = '700';
        this.flaggedCountEl.style.color = 'var(--peach-hot)';
      } else {
        this.flaggedCountEl.style.fontWeight = 'normal';
        this.flaggedCountEl.style.color = 'inherit';
      }
    }
    if (this.checkedCountEl) this.checkedCountEl.textContent = String(checkedCount);
    if (this.routineCountEl) this.routineCountEl.textContent = String(routineCount);

    // Highest risk
    let overallRisk = summary.overall_risk || 'None';
    if (overallRisk === 'None' && flaggedCount > 0) {
      overallRisk = 'Low';
    }
    if (this.highestRiskEl) {
      this.highestRiskEl.textContent = overallRisk;
      if (overallRisk.toLowerCase().includes('high')) {
        this.highestRiskEl.style.color = 'var(--peach-hot)';
      } else {
        this.highestRiskEl.style.color = 'inherit';
      }
    }

    // Input mode (capitalize)
    const mode = result.mode || 'text';
    const modeDisplay = mode.charAt(0).toUpperCase() + mode.slice(1);
    if (this.inputModeEl) this.inputModeEl.textContent = modeDisplay;

    // Elapsed time
    const elapsedMs = result.elapsed_ms != null ? result.elapsed_ms : 0;
    const elapsedSec = (elapsedMs / 1000).toFixed(1);
    if (this.elapsedTimeEl) this.elapsedTimeEl.textContent = `${elapsedSec} s`;

    // 5. Saved result notice (Section 7 Phase 7 point 6)
    const existingNotice = this.stripEl.querySelector('.saved-result-tag');
    if (existingNotice) existingNotice.remove();
    if (result._isSavedResult) {
      const tag = document.createElement('div');
      tag.className = 'saved-result-tag';
      tag.style.cssText = 'font-size: 10px; background: rgba(0,0,0,0.06); color: #666; border: 1px dashed #aaa; padding: 2px 6px; border-radius: 2px; margin-top: 8px; text-align: center;';
      tag.textContent = 'Saved result (demo replay)';
      this.stripEl.appendChild(tag);
    }

    // 6. Trigger print animation (respecting reduced motion)
    this.triggerPrintAnimation();
  }

  renderNotches(rank) {
    const filledCount = rank === 3 ? 3 : rank === 2 ? 2 : 1;
    return `
      <span class="receipt-notches" aria-hidden="true">
        <span class="receipt-notch ${filledCount >= 1 ? 'filled' : ''}"></span>
        <span class="receipt-notch ${filledCount >= 2 ? 'filled' : ''}"></span>
        <span class="receipt-notch ${filledCount >= 3 ? 'filled' : ''}"></span>
      </span>
    `;
  }

  triggerPrintAnimation() {
    if (!this.stripEl) return;
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReducedMotion) return;

    this.stripEl.classList.remove('printing');
    // Force DOM reflow to restart CSS animation
    void this.stripEl.offsetWidth;
    this.stripEl.classList.add('printing');

    // Remove class after animation finishes (700ms)
    setTimeout(() => {
      if (this.stripEl) {
        this.stripEl.classList.remove('printing');
      }
    }, 750);
  }

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
}
