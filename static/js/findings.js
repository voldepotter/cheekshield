/**
 * CheekShield AI — Evidence List & Findings Controller (Section 7 Phase 4)
 *
 * Renders flagged findings, routine pre-selections, and checked-fine items.
 * Handles:
 *  - Filtering by evidence kind (All, Model, Rule)
 *  - Filtering by category (chips)
 *  - Sorting by Risk (High->Low), Position (order), Score
 *  - Safe token attribution highlighting with orange alpha and hover tooltips
 *  - Rule evidence chips (dashed, raw weights, no %)
 *  - Collapsible ethical fixes and gate notes
 *  - Pagination for checked-fine items (50 per batch)
 *  - Clean state view when no manipulation found
 *  - Synchronized hover and focus with screenshot viewer
 */

import { getCategoryInfo, getAllDisplayCategories } from './categories.js';
import { store } from './state.js';

export class FindingsController {
  constructor(options = {}) {
    this.onRowHover = options.onRowHover || (() => {});
    this.onRowLeave = options.onRowLeave || (() => {});
    this.onShowOnScreenshot = options.onShowOnScreenshot || (() => {});

    // Elements
    this.resultsSection = document.getElementById('results-section');
    this.evidenceHeader = document.querySelector('.evidence-header');
    this.evidenceList = document.getElementById('evidence-list');
    this.filterSelect = document.getElementById('evidence-filter');
    this.sortSelect = document.getElementById('evidence-sort');
    this.categoryChipsContainer = document.getElementById('evidence-category-chips');

    // Routine pre-selections
    this.routineGroup = document.getElementById('routine-preselections-group');
    this.routineList = document.getElementById('routine-list');

    // Checked and fine
    this.checkedDetails = document.getElementById('checked-fine-details');
    this.checkedSummary = document.getElementById('checked-fine-summary');
    this.checkedList = document.getElementById('checked-fine-list');

    // Clean state box
    this.cleanStateBox = document.getElementById('clean-state-box');

    // Internal state
    this.currentResult = null;
    this.selectedCategories = new Set(); // empty means all
    this.activeFilter = 'all'; // all | model | rule
    this.activeSort = 'risk'; // risk | position | score
    this.checkedPage = 1;
    this.checkedPageSize = 50;

    this.initListeners();
  }

  initListeners() {
    if (this.filterSelect) {
      this.filterSelect.addEventListener('change', (e) => {
        this.activeFilter = e.target.value;
        store.set({ filterKind: this.activeFilter });
        this.renderFlaggedList();
      });
    }

    if (this.sortSelect) {
      this.sortSelect.addEventListener('change', (e) => {
        this.activeSort = e.target.value;
        store.set({ sortBy: this.activeSort });
        this.renderFlaggedList();
      });
    }
  }

  /**
   * Main render method called after audit completes.
   * @param {Object} result - Normalized API v1 response
   */
  render(result) {
    this.currentResult = result;
    if (!result) return;

    // Reveal results section
    if (this.resultsSection) {
      this.resultsSection.hidden = false;
    }

    const findings = result.findings || [];
    const summary = result.summary || {};

    // Render demo saved result banner if applicable (Section 7 Phase 7 point 6)
    let banner = document.getElementById('demo-saved-result-banner');
    if (result._isSavedResult) {
      if (!banner) {
        banner = document.createElement('div');
        banner.id = 'demo-saved-result-banner';
        banner.className = 'saved-result-banner';
        banner.innerHTML = '<span>Saved result (demo replay)</span><span>OFFLINE DEMO REPLAY</span>';
        const col = this.resultsSection?.querySelector('.results-evidence-col');
        if (col) col.prepend(banner);
      }
      banner.hidden = false;
    } else if (banner) {
      banner.hidden = true;
    }

    // Handle "no_content" status (Section 10)
    if (summary.status === 'no_content') {
      this.renderNoContentState(result);
      return;
    }

    const flagged = findings.filter((f) => f.kind === 'flag');
    const isClean = summary.status === 'clean' || flagged.length === 0;

    if (isClean) {
      this.renderCleanState(result);
    } else {
      if (this.cleanStateBox) this.cleanStateBox.hidden = true;
      if (this.evidenceHeader) this.evidenceHeader.hidden = false;
      if (this.evidenceList) this.evidenceList.hidden = false;

      this.renderCategoryChips(flagged);
      this.renderFlaggedList();
    }

    this.renderRoutinePreselections(findings);
    this.renderCheckedFine(findings);
  }

  renderNoContentState(result) {
    if (this.cleanStateBox) {
      this.cleanStateBox.hidden = false;
      const title = this.cleanStateBox.querySelector('.clean-title');
      const sub = this.cleanStateBox.querySelector('.clean-sub');
      if (title) title.textContent = 'Nothing to read yet.';
      if (sub) sub.textContent = 'The input contained no readable text blocks, interactive elements, or product details to audit.';
    }
    if (this.evidenceHeader) this.evidenceHeader.hidden = true;
    if (this.evidenceList) {
      this.evidenceList.innerHTML = '';
      this.evidenceList.hidden = true;
    }
    if (this.categoryChipsContainer) this.categoryChipsContainer.hidden = true;
    if (this.routineGroup) this.routineGroup.hidden = true;
    if (this.checkedDetails) this.checkedDetails.hidden = true;
  }

  // =========================================================================
  // Clean State Display (Mandatory Section 7 Phase 4)
  // =========================================================================
  renderCleanState(result) {
    if (this.cleanStateBox) this.cleanStateBox.hidden = false;
    if (this.evidenceHeader) this.evidenceHeader.hidden = true;
    if (this.evidenceList) {
      this.evidenceList.innerHTML = '';
      this.evidenceList.hidden = true;
    }

    const summary = result.summary || {};
    const checkedCount = summary.checked_fine || 0;
    const subEl = this.cleanStateBox.querySelector('.clean-sub');
    if (subEl) {
      subEl.innerHTML = `
        No deceptive patterns, countdown pressure, or hidden add-ons were detected across ${checkedCount} checked items.<br>
        <span style="display:inline-block; margin-top: 6px; opacity: 0.75;">This is not a guarantee. Hidden checkout steps and dynamic backend pricing cannot be seen from this snippet.</span>
      `;
    }
  }

  // =========================================================================
  // Category Filter Chips
  // =========================================================================
  renderCategoryChips(flaggedFindings) {
    if (!this.categoryChipsContainer) return;

    // Get unique categories present in flagged findings
    const presentCats = new Set(flaggedFindings.map((f) => f.category));
    if (presentCats.size <= 1) {
      this.categoryChipsContainer.innerHTML = '';
      this.categoryChipsContainer.hidden = true;
      return;
    }

    this.categoryChipsContainer.hidden = false;
    this.categoryChipsContainer.innerHTML = '';

    // "All" chip
    const allChip = document.createElement('button');
    allChip.type = 'button';
    allChip.className = `cat-chip ${this.selectedCategories.size === 0 ? 'active' : ''}`;
    allChip.textContent = `All (${flaggedFindings.length})`;
    allChip.addEventListener('click', () => {
      this.selectedCategories.clear();
      this.updateCategoryChipStates();
      this.renderFlaggedList();
    });
    this.categoryChipsContainer.appendChild(allChip);

    // One chip per present category
    for (const catName of presentCats) {
      const count = flaggedFindings.filter((f) => f.category === catName).length;
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = `cat-chip ${this.selectedCategories.has(catName) ? 'active' : ''}`;
      chip.dataset.category = catName;
      chip.textContent = `${catName} (${count})`;
      chip.addEventListener('click', () => {
        if (this.selectedCategories.has(catName)) {
          this.selectedCategories.delete(catName);
        } else {
          this.selectedCategories.add(catName);
        }
        this.updateCategoryChipStates();
        this.renderFlaggedList();
      });
      this.categoryChipsContainer.appendChild(chip);
    }
  }

  updateCategoryChipStates() {
    if (!this.categoryChipsContainer) return;
    const chips = this.categoryChipsContainer.querySelectorAll('.cat-chip');
    chips.forEach((chip) => {
      const cat = chip.dataset.category;
      if (!cat) {
        // "All" chip
        chip.classList.toggle('active', this.selectedCategories.size === 0);
      } else {
        chip.classList.toggle('active', this.selectedCategories.has(cat));
      }
    });
  }

  // =========================================================================
  // Flagged Findings Rendering & Filtering
  // =========================================================================
  renderFlaggedList() {
    if (!this.evidenceList || !this.currentResult) return;
    this.evidenceList.innerHTML = '';

    const findings = this.currentResult.findings || [];
    let items = findings.filter((f) => f.kind === 'flag');

    // 1. Filter by evidence kind (all, model, rule)
    if (this.activeFilter === 'model') {
      items = items.filter((f) => f.evidence_kind === 'model');
    } else if (this.activeFilter === 'rule') {
      items = items.filter((f) => f.evidence_kind === 'rule');
    }

    // 2. Filter by category chips
    if (this.selectedCategories.size > 0) {
      items = items.filter((f) => this.selectedCategories.has(f.category));
    }

    // 3. Sort
    if (this.activeSort === 'risk') {
      // Risk: High (3) -> Medium (2) -> Low (1), then score descending
      items.sort((a, b) => {
        const rankDiff = (b.risk_rank || 0) - (a.risk_rank || 0);
        if (rankDiff !== 0) return rankDiff;
        return (b.score || 0) - (a.score || 0);
      });
    } else if (this.activeSort === 'position') {
      // Document reading order
      items.sort((a, b) => (a.order || 0) - (b.order || 0));
    } else if (this.activeSort === 'score') {
      // Score descending
      items.sort((a, b) => (b.score || 0) - (a.score || 0));
    }

    if (items.length === 0) {
      const emptyNotice = document.createElement('div');
      emptyNotice.style.padding = 'var(--space-6) 0';
      emptyNotice.style.color = 'var(--white-dim)';
      emptyNotice.style.fontSize = 'var(--text-sm)';
      emptyNotice.textContent = 'No findings match the current filter.';
      this.evidenceList.appendChild(emptyNotice);
      return;
    }

    // Render each finding row
    for (const finding of items) {
      const row = this.createFindingRow(finding);
      this.evidenceList.appendChild(row);
    }
  }

  createFindingRow(finding) {
    const row = document.createElement('article');
    row.className = 'evidence-row';
    row.id = `evidence-row-${finding.id}`;
    row.dataset.findingId = finding.id;

    // Hover sync with screenshot bounding box
    row.addEventListener('mouseenter', () => {
      this.onRowHover(finding.id);
    });
    row.addEventListener('mouseleave', () => {
      this.onRowLeave(finding.id);
    });

    const catInfo = getCategoryInfo(finding.category);

    // Left Rail: glyph + notches + risk label
    const rail = document.createElement('div');
    rail.className = 'rail';

    const iconBox = document.createElement('div');
    iconBox.className = 'category-icon-box';
    iconBox.innerHTML = `<svg class="icon" aria-hidden="true"><use href="#${catInfo.glyph}" /></svg>`;

    const notchesBox = document.createElement('div');
    notchesBox.className = 'notches-box';
    notchesBox.setAttribute('aria-hidden', 'true');

    const rank = finding.risk_rank || 1;
    // 3 notches for High, 2 for Medium, 1 for Low, 0 for Benign
    if (rank === 3) {
      notchesBox.innerHTML = '<span class="notch filled"></span><span class="notch filled"></span><span class="notch filled"></span>';
    } else if (rank === 2) {
      notchesBox.innerHTML = '<span class="notch filled"></span><span class="notch filled"></span>';
    } else if (rank === 1) {
      notchesBox.innerHTML = '<span class="notch dashed"></span>';
    }

    const riskLabel = document.createElement('span');
    riskLabel.className = 'risk-label';
    riskLabel.style.fontSize = '11px';
    riskLabel.style.color = rank === 3 ? 'var(--peach-hot)' : rank === 2 ? 'var(--peach)' : 'var(--white-dim)';
    riskLabel.style.fontWeight = '600';
    riskLabel.textContent = rank === 3 ? 'High' : rank === 2 ? 'Medium' : 'Low';

    rail.appendChild(iconBox);
    rail.appendChild(notchesBox);
    rail.appendChild(riskLabel);

    // Content Block
    const content = document.createElement('div');
    content.className = 'evidence-content';

    // 1. Meta row: Category, Badge, Score, Show on Screenshot button
    const metaRow = document.createElement('div');
    metaRow.className = 'evidence-meta';

    const catTitle = document.createElement('span');
    catTitle.style.fontWeight = '700';
    catTitle.style.fontSize = 'var(--text-sm)';
    catTitle.textContent = finding.category;
    metaRow.appendChild(catTitle);

    const isModel = finding.evidence_kind === 'model';
    if (isModel) {
      const badge = document.createElement('span');
      badge.className = 'badge-model';
      badge.textContent = 'Model';
      metaRow.appendChild(badge);

      const conf = Math.round((finding.score || 0) * 100);
      const confTag = document.createElement('span');
      confTag.className = 'score-tag';
      confTag.textContent = `Confidence ${conf}%`;
      metaRow.appendChild(confTag);

      if (finding.p_dark != null) {
        const pDark = Math.round(finding.p_dark * 100);
        const pDarkTag = document.createElement('span');
        pDarkTag.className = 'score-tag';
        pDarkTag.textContent = `Dark probability ${pDark}%`;
        metaRow.appendChild(pDarkTag);
      }
    } else {
      const badge = document.createElement('span');
      badge.className = 'badge-rule';
      badge.textContent = 'Rule';
      metaRow.appendChild(badge);

      const ruleScoreTag = document.createElement('span');
      ruleScoreTag.className = 'score-tag';
      ruleScoreTag.title = 'A heuristic, not a probability';
      ruleScoreTag.textContent = `Rule score ${(finding.score || 0).toFixed(2)}`;
      metaRow.appendChild(ruleScoreTag);
    }

    // "Show on screenshot" button if bbox exists
    if (finding.bbox) {
      const showBtn = document.createElement('button');
      showBtn.type = 'button';
      showBtn.className = 'btn-show-bbox';
      showBtn.textContent = 'Show on screenshot';
      showBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.onShowOnScreenshot(finding.id);
      });
      metaRow.appendChild(showBtn);
    }

    content.appendChild(metaRow);

    // 2. Quote block with token highlight (pure textContent construction for security)
    const quoteBlock = this.createQuoteBlock(finding);
    content.appendChild(quoteBlock);

    // 3. Verdict line
    if (finding.verdict) {
      const verdict = document.createElement('p');
      verdict.className = 'verdict-line';
      verdict.textContent = finding.verdict;
      content.appendChild(verdict);
    }

    // 4. Explanation
    if (finding.explanation) {
      const explanation = document.createElement('p');
      explanation.className = 'explanation-text';
      explanation.textContent = finding.explanation;
      content.appendChild(explanation);
    }

    // 5. Collapsible Ethical Fix
    if (finding.how_to_fix) {
      const fixDetails = document.createElement('details');
      fixDetails.className = 'fix-disclosure';

      const fixSummary = document.createElement('summary');
      fixSummary.className = 'fix-summary';
      fixSummary.textContent = 'Ethical fix';

      const fixBody = document.createElement('div');
      fixBody.className = 'fix-body';

      const fixText = document.createElement('div');
      fixText.textContent = finding.how_to_fix;
      fixBody.appendChild(fixText);

      // Stretch: Before/After comparison mock for Urgency, Preselected Choice, Misdirection
      const comparisonEl = this.createEthicalComparison(finding.category);
      if (comparisonEl) {
        fixBody.appendChild(comparisonEl);
      }

      fixDetails.appendChild(fixSummary);
      fixDetails.appendChild(fixBody);
      content.appendChild(fixDetails);
    }

    // 6. Why this was kept (gate note disclosure)
    if (finding.gate_note) {
      const gateDetails = document.createElement('details');
      gateDetails.className = 'fix-disclosure';
      gateDetails.style.marginTop = '4px';

      const gateSummary = document.createElement('summary');
      gateSummary.className = 'fix-summary';
      gateSummary.textContent = 'Why this was kept';

      const gateBody = document.createElement('div');
      gateBody.className = 'fix-body';
      gateBody.textContent = finding.gate_note;

      gateDetails.appendChild(gateSummary);
      gateDetails.appendChild(gateBody);
      content.appendChild(gateDetails);
    }

    row.appendChild(rail);
    row.appendChild(content);

    return row;
  }

  // =========================================================================
  // Safe Token Highlighting & Quote Construction (Anti-XSS textContent only)
  // =========================================================================
  createQuoteBlock(finding) {
    const wrapper = document.createElement('div');
    const quote = document.createElement('blockquote');
    quote.className = 'quote-block';

    const rawText = finding.text || '';
    const attributions = finding.attributions || [];

    if (finding.evidence_kind === 'model') {
      // Model findings: highlight tokens with weight >= 0.05
      const significantTokens = attributions.filter((a) => (a.weight || 0) >= 0.05 && a.token);

      if (significantTokens.length === 0) {
        quote.textContent = rawText;
      } else {
        // Find positions of significant tokens inside rawText
        this.renderHighlightedText(quote, rawText, significantTokens);
      }

      wrapper.appendChild(quote);

      if (significantTokens.length > 0) {
        const legend = document.createElement('div');
        legend.className = 'attr-legend';
        legend.textContent = 'Highlighted words contributed most to this prediction.';
        wrapper.appendChild(legend);
      }
    } else {
      // Rule findings: plain text quote + rule chips below
      quote.textContent = rawText;
      wrapper.appendChild(quote);

      if (attributions.length > 0) {
        const chipsList = document.createElement('div');
        chipsList.className = 'rule-chips-list';

        for (const attr of attributions) {
          const chip = document.createElement('span');
          chip.className = 'rule-chip';
          const weightDisplay = typeof attr.weight === 'number' ? attr.weight.toFixed(2) : attr.weight;
          chip.textContent = `${attr.token} (weight ${weightDisplay})`;
          chipsList.appendChild(chip);
        }
        wrapper.appendChild(chipsList);
      }
    }

    return wrapper;
  }

  renderHighlightedText(container, text, tokens) {
    // Sort tokens by length descending to match longer phrases first
    const sortedTokens = [...tokens].sort((a, b) => (b.token?.length || 0) - (a.token?.length || 0));

    // Find occurrences
    const matches = [];
    const textLower = text.toLowerCase();

    for (const item of sortedTokens) {
      const tok = item.token;
      if (!tok) continue;
      const tokLower = tok.toLowerCase();
      let pos = 0;
      while ((pos = textLower.indexOf(tokLower, pos)) !== -1) {
        const end = pos + tok.length;
        // Check overlap with existing matches
        const overlap = matches.some((m) => Math.max(m.start, pos) < Math.min(m.end, end));
        if (!overlap) {
          matches.push({ start: pos, end, item });
        }
        pos = end;
      }
    }

    // Sort matches by start index
    matches.sort((a, b) => a.start - b.start);

    if (matches.length === 0) {
      container.textContent = text;
      return;
    }

    let currentIndex = 0;
    for (const m of matches) {
      if (m.start > currentIndex) {
        container.appendChild(document.createTextNode(text.slice(currentIndex, m.start)));
      }

      const span = document.createElement('span');
      span.className = 'attr-token';
      const weight = m.item.weight || 0;
      const alpha = Math.min(0.85, Math.max(0.18, weight * 0.9)).toFixed(2);
      span.style.setProperty('--alpha', alpha);
      const pct = Math.round(weight * 100);
      span.title = `removing this word lowers the score by ${pct}%`;
      span.tabIndex = 0;
      span.textContent = text.slice(m.start, m.end);
      container.appendChild(span);

      currentIndex = m.end;
    }

    if (currentIndex < text.length) {
      container.appendChild(document.createTextNode(text.slice(currentIndex)));
    }
  }

  // =========================================================================
  // Routine Pre-selections (Muted, Visible)
  // =========================================================================
  renderRoutinePreselections(findings) {
    const routineItems = findings.filter((f) => f.kind === 'routine_preselection');

    if (!this.routineGroup || !this.routineList) return;

    if (routineItems.length === 0) {
      this.routineGroup.hidden = true;
      this.routineList.innerHTML = '';
      return;
    }

    this.routineGroup.hidden = false;
    this.routineList.innerHTML = '';

    for (const item of routineItems) {
      const row = document.createElement('div');
      row.className = 'evidence-row routine-item';
      row.style.opacity = '0.7';

      const rail = document.createElement('div');
      rail.className = 'rail';
      const iconBox = document.createElement('div');
      iconBox.className = 'category-icon-box';
      iconBox.style.color = 'var(--white-dim)';
      iconBox.innerHTML = '<svg class="icon"><use href="#glyph-preselected-choice" /></svg>';
      rail.appendChild(iconBox);

      const content = document.createElement('div');
      content.className = 'evidence-content';

      const meta = document.createElement('div');
      meta.className = 'evidence-meta';
      meta.innerHTML = `
        <span style="font-weight: 600;">Routine Pre-selection</span>
        <span class="badge-rule">Rule</span>
        <span class="score-tag">Benign convenience</span>
      `;
      content.appendChild(meta);

      const quote = document.createElement('blockquote');
      quote.className = 'quote-block';
      quote.style.borderLeftColor = 'var(--hairline-strong)';
      quote.textContent = item.text || '';
      content.appendChild(quote);

      if (item.explanation) {
        const exp = document.createElement('p');
        exp.className = 'explanation-text';
        exp.textContent = item.explanation;
        content.appendChild(exp);
      }

      row.appendChild(rail);
      row.appendChild(content);
      this.routineList.appendChild(row);
    }
  }

  // =========================================================================
  // Checked and Fine (Collapsed details, paginated at 50)
  // =========================================================================
  renderCheckedFine(findings) {
    const checkedItems = findings.filter((f) => f.kind === 'checked');

    if (!this.checkedDetails || !this.checkedList || !this.checkedSummary) return;

    if (checkedItems.length === 0) {
      this.checkedDetails.hidden = true;
      this.checkedList.innerHTML = '';
      return;
    }

    this.checkedDetails.hidden = false;
    this.checkedSummary.textContent = `Checked and fine (${checkedItems.length})`;
    this.checkedList.innerHTML = '';
    this.checkedPage = 1;

    this.renderCheckedPage(checkedItems);
  }

  renderCheckedPage(checkedItems) {
    const countToRender = Math.min(this.checkedPage * this.checkedPageSize, checkedItems.length);
    const slice = checkedItems.slice(0, countToRender);

    this.checkedList.innerHTML = '';

    for (const item of slice) {
      const div = document.createElement('div');
      div.style.padding = 'var(--space-2) var(--space-3)';
      div.style.borderBottom = '1px solid var(--hairline)';
      div.style.fontSize = 'var(--text-xs)';
      div.style.color = 'var(--white-dim)';
      div.style.display = 'flex';
      div.style.justifyContent = 'space-between';
      div.style.gap = 'var(--space-3)';

      const textSpan = document.createElement('span');
      textSpan.style.fontFamily = 'var(--font-mono)';
      textSpan.textContent = item.text || '(empty block)';

      const okBadge = document.createElement('span');
      okBadge.style.color = 'var(--leaf)';
      okBadge.textContent = 'Clear';

      div.appendChild(textSpan);
      div.appendChild(okBadge);
      this.checkedList.appendChild(div);
    }

    // Pagination button if more items remain
    if (countToRender < checkedItems.length) {
      const moreBtn = document.createElement('button');
      moreBtn.type = 'button';
      moreBtn.className = 'receipt-btn';
      moreBtn.style.marginTop = 'var(--space-3)';
      moreBtn.style.alignSelf = 'center';
      moreBtn.textContent = `Show more (${checkedItems.length - countToRender} remaining)`;
      moreBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.checkedPage++;
        this.renderCheckedPage(checkedItems);
      });
      this.checkedList.appendChild(moreBtn);
    }
  }

  /**
   * Highlight a finding row when its bounding box is hovered in viewer.
   */
  highlightFindingRow(findingId, scrollIntoView = false) {
    if (!this.evidenceList) return;
    const rows = this.evidenceList.querySelectorAll('.evidence-row');
    rows.forEach((r) => {
      const matches = r.dataset.findingId === findingId;
      r.classList.toggle('highlighted', matches);
      if (matches && scrollIntoView) {
        r.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
  }

  clearFindingRowHighlight() {
    if (!this.evidenceList) return;
    const rows = this.evidenceList.querySelectorAll('.evidence-row.highlighted');
    rows.forEach((r) => r.classList.remove('highlighted'));
  }

  /**
   * Stretch (Section 7 Phase 6): Before & After static UI comparison mocks
   * for Urgency, Preselected Choice, and Misdirection.
   * Pure static HTML/CSS, zero user data rendered inside.
   */
  createEthicalComparison(category) {
    const cat = (category || '').toLowerCase();
    if (cat !== 'urgency' && cat !== 'preselected choice' && cat !== 'misdirection') {
      return null;
    }

    const wrap = document.createElement('div');
    wrap.className = 'ethical-comparison-wrap';

    const hdr = document.createElement('div');
    hdr.className = 'comparison-header';
    hdr.textContent = 'Design Pattern Comparison (Before / After)';
    wrap.appendChild(hdr);

    const grid = document.createElement('div');
    grid.className = 'comparison-grid';

    // Dark side card
    const darkCard = document.createElement('div');
    darkCard.className = 'comparison-card dark';
    darkCard.innerHTML = '<span class="comparison-tag dark">Manipulative Pattern</span>';

    // Ethical side card
    const ethicalCard = document.createElement('div');
    ethicalCard.className = 'comparison-card ethical';
    ethicalCard.innerHTML = '<span class="comparison-tag ethical">Ethical Pattern</span>';

    if (cat === 'urgency') {
      const darkUi = document.createElement('div');
      darkUi.className = 'mock-ui';
      darkUi.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; color:var(--peach-hot); font-weight:700; font-size:11px;">
          <span>⏱ Ends in 04:59!</span>
          <span style="font-size:10px; color:#fff;">Only 2 left</span>
        </div>
        <div style="font-size:10px; color:var(--white-dim); margin-top:4px;">12 people are looking at this right now!</div>
      `;
      darkCard.appendChild(darkUi);

      const ethicalUi = document.createElement('div');
      ethicalUi.className = 'mock-ui';
      ethicalUi.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; color:var(--leaf); font-weight:600; font-size:11px;">
          <span>✓ In Stock</span>
          <span style="font-size:10px; color:var(--white-dim);">Standard Shipping</span>
        </div>
        <div style="font-size:10px; color:var(--white-dim); margin-top:4px;">Sale price valid through catalog dates. Free returns within 30 days.</div>
      `;
      ethicalCard.appendChild(ethicalUi);
    } else if (cat === 'preselected choice') {
      const darkUi = document.createElement('div');
      darkUi.className = 'mock-ui';
      darkUi.innerHTML = `
        <label style="display:flex; align-items:center; gap:6px; font-size:11px; cursor:default;">
          <input type="checkbox" checked disabled>
          <span>Add Rs 199 protection</span>
        </label>
        <div style="font-size:9px; color:#777; margin-top:4px;">Auto-renews annually. Non-refundable.</div>
      `;
      darkCard.appendChild(darkUi);

      const ethicalUi = document.createElement('div');
      ethicalUi.className = 'mock-ui';
      ethicalUi.innerHTML = `
        <label style="display:flex; align-items:center; gap:6px; font-size:11px; cursor:default;">
          <input type="checkbox" disabled>
          <span>Add accidental protection plan (Rs 199/yr)</span>
        </label>
        <div style="font-size:9px; color:var(--leaf); margin-top:4px;">Optional add-on. Cancel anytime with one click.</div>
      `;
      ethicalCard.appendChild(ethicalUi);
    } else if (cat === 'misdirection') {
      const darkUi = document.createElement('div');
      darkUi.className = 'mock-ui';
      darkUi.innerHTML = `
        <button type="button" style="width:100%; padding:6px; background:var(--peach); color:#000; font-weight:700; border:none; border-radius:2px; font-size:11px;">Keep my subscription</button>
        <div style="text-align:center; margin-top:6px; font-size:9px; color:#666; text-decoration:underline;">No thanks, I don't care about saving money</div>
      `;
      darkCard.appendChild(darkUi);

      const ethicalUi = document.createElement('div');
      ethicalUi.className = 'mock-ui';
      ethicalUi.innerHTML = `
        <div style="display:flex; gap:6px;">
          <button type="button" style="flex:1; padding:6px; background:var(--ink-1); border:1px solid var(--hairline-strong); color:#fff; font-size:11px; border-radius:2px;">Keep subscription</button>
          <button type="button" style="flex:1; padding:6px; background:var(--ink-1); border:1px solid var(--hairline-strong); color:var(--white-dim); font-size:11px; border-radius:2px;">Cancel subscription</button>
        </div>
      `;
      ethicalCard.appendChild(ethicalUi);
    }

    grid.appendChild(darkCard);
    grid.appendChild(ethicalCard);
    wrap.appendChild(grid);
    return wrap;
  }
}
