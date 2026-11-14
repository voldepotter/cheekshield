/**
 * CheekShield AI — Audit Export Controller (Section 7 Phase 6)
 *
 * Handles:
 *  - Download JSON: formatted export with audit data, model info, timestamp, disclaimer,
 *    with option to include or exclude annotated screenshot data URL.
 *  - Save as PDF: triggers window.print() styled via print.css
 *  - Copy Summary: plain text clipboard summary
 *  - Fixed filename pattern: cheekshield-audit-YYYYMMDD-HHMM.json
 */

import { store } from './state.js';

export class ExportController {
  constructor() {
    this.downloadJsonBtn = document.getElementById('download-json-btn');
    this.savePdfBtn = document.getElementById('save-pdf-btn');
    this.copySummaryBtn = document.getElementById('copy-summary-btn');
    this.includeImageCheckbox = document.getElementById('export-include-image');

    this.init();
  }

  init() {
    if (this.downloadJsonBtn) {
      this.downloadJsonBtn.addEventListener('click', () => this.downloadJson());
    }

    if (this.savePdfBtn) {
      this.savePdfBtn.addEventListener('click', () => this.savePdf());
    }

    if (this.copySummaryBtn) {
      this.copySummaryBtn.addEventListener('click', () => this.copySummary());
    }
  }

  downloadJson() {
    const { currentResult } = store.get();
    if (!currentResult) {
      alert('Run an audit first before downloading results.');
      return;
    }

    const now = new Date();
    const timestampStr = this.formatTimestamp(now);

    // Deep clone to safely manipulate options
    const auditCopy = JSON.parse(JSON.stringify(currentResult));

    // Check include image preference
    const includeImage = this.includeImageCheckbox ? this.includeImageCheckbox.checked : true;
    if (!includeImage && auditCopy.screenshot?.annotated) {
      delete auditCopy.screenshot.annotated;
      auditCopy.screenshot.image_omitted = true;
    }

    const exportData = {
      app: 'CheekShield AI',
      version: '1.0',
      exported_at: now.toISOString(),
      disclaimer: 'Assistive indication of potentially deceptive design, not a legal finding. Every flagged item warrants human review.',
      audit: auditCopy,
    };

    const jsonStr = JSON.stringify(exportData, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const link = document.createElement('a');
    link.href = url;
    link.download = `cheekshield-audit-${timestampStr}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  savePdf() {
    window.print();
  }

  async copySummary() {
    const { currentResult } = store.get();
    if (!currentResult) {
      alert('Run an audit first before copying summary.');
      return;
    }

    const exposure = currentResult.exposure || {};
    const summary = currentResult.summary || {};
    const findings = currentResult.findings || [];
    const flagged = findings.filter((f) => f.kind === 'flag');

    // Build category summary
    const catCounts = {};
    for (const f of flagged) {
      catCounts[f.category] = (catCounts[f.category] || 0) + 1;
    }
    const catBreakdown = Object.entries(catCounts)
      .map(([cat, count]) => `${cat} (${count})`)
      .join(', ') || 'None';

    const text = [
      '--- CHEEKSHIELD AI AUDIT SUMMARY ---',
      `Cheekometer Exposure: ${exposure.percent ?? 0}% (${exposure.label || 'Fresh'})`,
      `Flagged dark patterns: ${summary.flagged_items ?? flagged.length}`,
      `Highest risk tier: ${summary.overall_risk || 'None'}`,
      `Checked & fine items: ${summary.checked_fine ?? 0}`,
      `Routine pre-selections: ${summary.routine_preselections ?? 0}`,
      `Breakdown: ${catBreakdown}`,
      `Analysis time: ${((currentResult.elapsed_ms || 0) / 1000).toFixed(1)}s (${currentResult.mode || 'text'})`,
      '------------------------------------',
      'Assistive indication, not a legal finding. Every flagged item warrants human review.',
    ].join('\n');

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        // Fallback
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }

      if (this.copySummaryBtn) {
        const origText = this.copySummaryBtn.textContent;
        this.copySummaryBtn.textContent = 'Copied!';
        setTimeout(() => {
          if (this.copySummaryBtn) this.copySummaryBtn.textContent = origText;
        }, 1500);
      }
    } catch (err) {
      console.warn('Failed to copy summary to clipboard:', err);
    }
  }

  formatTimestamp(date) {
    const pad = (n) => String(n).padStart(2, '0');
    const y = date.getFullYear();
    const m = pad(date.getMonth() + 1);
    const d = pad(date.getDate());
    const h = pad(date.getHours());
    const min = pad(date.getMinutes());
    return `${y}${m}${d}-${h}${min}`;
  }
}
