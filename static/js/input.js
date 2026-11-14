/**
 * CheekShield AI — Input Panel Controller (Section 7 Phase 2)
 */

import { store } from './state.js';
import { fetchSamples, postAnalyze } from './api.js';

const LIMITS = {
  textMaxChars: 20000,
  htmlMaxBytes: 4 * 1024 * 1024, // 400 KB
  imageMaxBytes: 8 * 1024 * 1024, // 8 MB
  allowedImageTypes: ['image/png', 'image/jpeg', 'image/webp'],
};

export class InputController {
  constructor() {
    this.abortController = null;
    this.auditSeq = 0;
    // Default samples immediately available synchronously
    this.samples = [
      {
        id: 'text_deceptive',
        mode: 'text',
        expected: 'deceptive',
        content: "Hurry! Only 2 left in stock.\n8 people are viewing this item right now.\nOffer ends in 04:59. Don't miss out!\nAdd Rs 199 order protection\nNo thanks, I prefer paying full price."
      },
      {
        id: 'text_clean',
        mode: 'text',
        expected: 'clean',
        content: "Ships in 2 business days.\nFree returns within 30 days of delivery.\nOrder summary\nPrice includes all taxes.\nAdd to cart"
      },
      {
        id: 'html_deceptive',
        mode: 'html',
        expected: 'deceptive',
        content: `<div class="order-protection">\n  <label><input type="checkbox" checked> Add Rs 199 order protection</label>\n</div>\n<div class="remember">\n  <label><input type="checkbox" checked> Remember me</label>\n</div>\n<div class="fine-print">\n  <span style="font-size:9px; color:#bbb; background:#fff">auto-renews at Rs 999/year</span>\n</div>\n<div class="actions">\n  <button style="padding:16px 48px; font-size:18px; background:#ff6600; color:#fff;">Keep my plan</button>\n  <a href="#" style="font-size:11px; color:#999;">No thanks, I don't like saving money</a>\n</div>`
      },
      {
        id: 'html_clean',
        mode: 'html',
        expected: 'clean',
        content: `<h1>Wireless Bluetooth Headphones</h1>\n<p class="price">Rs 2,499</p>\n<p class="description">Over-ear headphones with active noise cancellation.</p>\n<p class="shipping">Free shipping on orders above Rs 500.</p>\n<p class="returns">Free returns within 30 days of delivery.</p>\n<label><input type="checkbox"> Subscribe to our newsletter</label>\n<button>Add to cart</button>`
      }
    ];

    // Elements
    this.tabs = Array.from(document.querySelectorAll('[role="tab"]'));
    this.panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));

    // Text tab
    this.textInput = document.getElementById('text-input');
    this.textCharCount = document.getElementById('text-char-count');
    this.textLineCount = document.getElementById('text-line-count');
    this.textClearBtn = document.getElementById('text-clear-btn');

    // HTML tab
    this.htmlInput = document.getElementById('html-input');
    this.htmlSizeCount = document.getElementById('html-size-count');
    this.htmlFileInput = document.getElementById('html-file-input');
    this.htmlFilename = document.getElementById('html-filename');
    this.htmlClearBtn = document.getElementById('html-clear-btn');

    // Screenshot tab
    this.dropzone = document.getElementById('dropzone');
    this.screenshotFileInput = document.getElementById('screenshot-file-input');
    this.screenshotPreview = document.getElementById('screenshot-preview');
    this.previewImg = document.getElementById('preview-img');
    this.previewName = document.getElementById('preview-name');
    this.previewSize = document.getElementById('preview-size');
    this.removeScreenshotBtn = document.getElementById('remove-screenshot-btn');

    // Action row
    this.btnAudit = document.getElementById('btn-audit');
    this.btnAuditLabel = document.getElementById('btn-audit-label');
    this.btnCancel = document.getElementById('btn-cancel');
    this.sampleDeceptiveBtn = document.getElementById('sample-deceptive-btn');
    this.sampleCleanBtn = document.getElementById('sample-clean-btn');

    // Error banner container
    this.errorBanner = document.getElementById('input-error-banner');
    this.errorText = document.getElementById('input-error-text');

    this.init();
  }

  async init() {
    this.setupTabsAccessibility();
    this.setupTextInput();
    this.setupHtmlInput();
    this.setupScreenshotInput();
    this.setupAuditButton();
    this.setupSampleButtons();
    this.updateAuditButtonState();
    await this.loadSamples();

    // Subscribe to state updates
    store.subscribe((curr, prev) => {
      if (curr.mode !== prev.mode) {
        this.clearError();
        this.updateAuditButtonState();
      }
    });
  }

  // =========================================================================
  // 1. Segmented Tabs & Keyboard Navigation (Section 7 Phase 2.1)
  // =========================================================================
  setupTabsAccessibility() {
    this.tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => this.switchTab(index));

      tab.addEventListener('keydown', (e) => {
        let targetIndex = null;
        if (e.key === 'ArrowRight') {
          targetIndex = (index + 1) % this.tabs.length;
        } else if (e.key === 'ArrowLeft') {
          targetIndex = (index - 1 + this.tabs.length) % this.tabs.length;
        } else if (e.key === 'Home') {
          targetIndex = 0;
        } else if (e.key === 'End') {
          targetIndex = this.tabs.length - 1;
        }

        if (targetIndex !== null) {
          e.preventDefault();
          this.switchTab(targetIndex);
          this.tabs[targetIndex].focus();
        }
      });
    });
  }

  switchTab(index) {
    this.tabs.forEach((t, i) => {
      const selected = i === index;
      t.setAttribute('aria-selected', selected ? 'true' : 'false');
      t.setAttribute('tabindex', selected ? '0' : '-1');
    });

    this.panels.forEach((p, i) => {
      p.hidden = i !== index;
    });

    const modes = ['text', 'html', 'screenshot'];
    const mode = modes[index];
    store.set({ mode });

    if (mode === 'screenshot') {
      this.checkOcrNotice();
    } else {
      this.hideOcrNotice();
    }
  }

  checkOcrNotice() {
    const { ocrReady } = store.get();
    let banner = document.getElementById('ocr-notice-banner');
    if (ocrReady === false) {
      if (!banner) {
        banner = document.createElement('div');
        banner.id = 'ocr-notice-banner';
        banner.className = 'ocr-notice-banner';
        banner.setAttribute('role', 'status');
        banner.textContent = 'OCR engine is not loaded on this server. Text and HTML auditing remain operational.';
        const panel = document.getElementById('panel-screenshot');
        if (panel) panel.prepend(banner);
      }
      banner.hidden = false;
    } else if (banner) {
      banner.hidden = true;
    }
  }

  hideOcrNotice() {
    const banner = document.getElementById('ocr-notice-banner');
    if (banner) banner.hidden = true;
  }

  // =========================================================================
  // 2. Text Input (Section 7 Phase 2.2)
  // =========================================================================
  setupTextInput() {
    const onTextInput = () => {
      const val = this.textInput.value;
      store.set({ textContent: val });

      const chars = val.length;
      this.textCharCount.textContent = `${chars.toLocaleString()} / ${LIMITS.textMaxChars.toLocaleString()} chars`;

      const lines = val ? val.split(/\r\n|\r|\n/).length : 0;
      this.textLineCount.textContent = `${lines} ${lines === 1 ? 'line' : 'lines'}`;

      if (chars > LIMITS.textMaxChars) {
        this.showError(`Text is ${chars.toLocaleString()} characters. Maximum is ${LIMITS.textMaxChars.toLocaleString()}. Shorten the input.`);
      } else {
        this.clearError();
      }

      this.updateAuditButtonState();
    };

    this.textInput.addEventListener('input', onTextInput);
    this.textInput.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        this.triggerAudit();
      }
    });

    this.textClearBtn.addEventListener('click', () => {
      this.textInput.value = '';
      this.clearError();
      onTextInput();
      this.textInput.focus();
    });
  }

  // =========================================================================
  // 3. HTML Input (Section 7 Phase 2.3)
  // =========================================================================
  setupHtmlInput() {
    const onHtmlInput = () => {
      const val = this.htmlInput.value;
      store.set({ htmlContent: val });

      const bytes = new Blob([val]).size;
      const kb = Math.round(bytes / 1024);
      const limitKb = LIMITS.htmlMaxBytes / 1024;
      this.htmlSizeCount.textContent = `${kb} / ${limitKb} KB`;

      if (bytes > LIMITS.htmlMaxBytes) {
        this.showError(`HTML is ${kb} KB. Maximum is ${limitKb} KB. Remove scripts, images, and stylesheets.`);
      } else {
        this.clearError();
      }

      this.updateAuditButtonState();
    };

    this.htmlInput.addEventListener('input', onHtmlInput);
    this.htmlInput.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        this.triggerAudit();
      }
    });

    this.htmlClearBtn.addEventListener('click', () => {
      this.htmlInput.value = '';
      this.htmlFilename.textContent = 'No file selected';
      this.htmlFileInput.value = '';
      this.clearError();
      onHtmlInput();
      this.htmlInput.focus();
    });

    // File upload
    this.htmlFileInput.addEventListener('change', (e) => {
      const file = e.target.files?.[0];
      if (!file) return;

      this.htmlFilename.textContent = file.name;
      const reader = new FileReader();
      reader.onload = (event) => {
        this.htmlInput.value = event.target.result;
        onHtmlInput();
      };
      reader.onerror = () => {
        this.showError('Failed to read the HTML file.');
      };
      reader.readAsText(file);
    });
  }

  // =========================================================================
  // 4. Screenshot Input (Section 7 Phase 2.4)
  // =========================================================================
  setupScreenshotInput() {
    // Click dropzone to open chooser
    this.dropzone.addEventListener('click', () => {
      this.screenshotFileInput.click();
    });

    this.dropzone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.screenshotFileInput.click();
      }
    });

    // Drag and drop
    ['dragenter', 'dragover'].forEach((eventName) => {
      this.dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.dropzone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach((eventName) => {
      this.dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.dropzone.classList.remove('dragover');
      });
    });

    this.dropzone.addEventListener('drop', (e) => {
      const file = e.dataTransfer?.files?.[0];
      if (file) {
        this.handleImageFile(file);
      }
    });

    // File input change
    this.screenshotFileInput.addEventListener('change', (e) => {
      const file = e.target.files?.[0];
      if (file) {
        this.handleImageFile(file);
      }
    });

    // Remove button
    this.removeScreenshotBtn.addEventListener('click', () => {
      this.clearScreenshot();
      this.clearError();
      this.updateAuditButtonState();
    });

    // Global Paste (Ctrl+V / Cmd+V)
    window.addEventListener('paste', (e) => {
      const items = e.clipboardData?.items;
      if (!items) return;

      for (let i = 0; i < items.length; i++) {
        if (items[i].type.startsWith('image/')) {
          const file = items[i].getAsFile();
          if (file) {
            e.preventDefault();
            this.switchTab(2); // Switch to screenshot tab
            this.handleImageFile(file);
            break;
          }
        }
      }
    });
  }

  handleImageFile(file) {
    this.clearError();

    // Type validation
    if (!LIMITS.allowedImageTypes.includes(file.type)) {
      this.showError('That file is not a PNG, JPEG or WEBP image.');
      return;
    }

    // Size validation
    if (file.size > LIMITS.imageMaxBytes) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
      this.showError(`Image is ${sizeMb} MB. Maximum is 8 MB.`);
      return;
    }

    // Read and preview
    const url = URL.createObjectURL(file);
    this.previewImg.src = url;
    this.previewName.textContent = file.name || 'Pasted image';
    const displaySize = file.size > 1024 * 1024
      ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
      : `${Math.round(file.size / 1024)} KB`;
    this.previewSize.textContent = displaySize;

    this.dropzone.hidden = true;
    this.screenshotPreview.hidden = false;

    store.set({
      screenshotFile: file,
      screenshotPreviewUrl: url,
    });

    this.updateAuditButtonState();
  }

  clearScreenshot() {
    const { screenshotPreviewUrl } = store.get();
    if (screenshotPreviewUrl) {
      URL.revokeObjectURL(screenshotPreviewUrl);
    }
    this.previewImg.src = '';
    this.screenshotFileInput.value = '';
    this.screenshotPreview.hidden = true;
    this.dropzone.hidden = false;

    store.set({
      screenshotFile: null,
      screenshotPreviewUrl: null,
    });
  }

  // =========================================================================
  // 5. Samples (Section 7 Phase 2.5, Section 11)
  // =========================================================================
  async loadSamples() {
    try {
      const fetched = await fetchSamples();
      if (fetched && Array.isArray(fetched) && fetched.length > 0) {
        this.samples = fetched;
      }
    } catch (err) {
      // Offline fallback samples already populated
    }
  }

  setupSampleButtons() {
    this.sampleDeceptiveBtn.addEventListener('click', () => this.applySample('deceptive'));
    this.sampleCleanBtn.addEventListener('click', () => this.applySample('clean'));
  }

  async applySample(expectedType) {
    const { mode } = store.get();
    const sample = this.samples.find(
      (s) => s.mode === mode && s.expected === expectedType
    );

    if (!sample) return;

    if (mode === 'text') {
      this.textInput.value = sample.content || '';
      this.textInput.dispatchEvent(new Event('input'));
    } else if (mode === 'html') {
      this.htmlInput.value = sample.content || '';
      this.htmlFilename.textContent = `${sample.id}.html`;
      this.htmlInput.dispatchEvent(new Event('input'));
    } else if (mode === 'screenshot' && sample.file) {
      try {
        const res = await fetch(sample.file);
        const blob = await res.blob();
        const file = new File([blob], `${sample.id}.png`, { type: 'image/png' });
        this.handleImageFile(file);
      } catch (err) {
        console.warn('Failed to load sample image:', err);
      }
    }
  }

  // =========================================================================
  // 6. Audit Button & Actions (Section 7 Phase 2.6)
  // =========================================================================
  setupAuditButton() {
    this.btnAudit.addEventListener('click', () => this.triggerAudit());

    this.btnCancel.addEventListener('click', () => {
      if (this.abortController) {
        this.abortController.abort();
      }
    });
  }

  updateAuditButtonState() {
    const { mode, textContent, htmlContent, screenshotFile, isAuditing } = store.get();

    if (isAuditing) {
      this.btnAudit.disabled = true;
      this.btnAudit.classList.add('auditing');
      this.btnAuditLabel.textContent = 'Auditing';
      this.btnCancel.hidden = false;
      return;
    }

    this.btnAudit.classList.remove('auditing');
    this.btnAuditLabel.textContent = 'Audit';
    this.btnCancel.hidden = true;

    let hasContent = false;
    let hasError = !this.errorBanner.hidden;

    if (mode === 'text') {
      hasContent = Boolean(textContent && textContent.trim());
    } else if (mode === 'html') {
      hasContent = Boolean(htmlContent && htmlContent.trim());
    } else if (mode === 'screenshot') {
      hasContent = Boolean(screenshotFile);
    }

    const canSubmit = hasContent && !hasError;
    this.btnAudit.disabled = !canSubmit;
    this.btnAudit.title = canSubmit ? 'Press to audit (Ctrl+Enter)' : 'Add something to audit';
  }

  async triggerAudit() {
    const { mode, textContent, htmlContent, screenshotFile, isAuditing } = store.get();
    if (isAuditing) return; // Prevent double submit

    let content = '';
    let file = null;

    if (mode === 'text') {
      content = textContent.trim();
      if (!content) return;
    } else if (mode === 'html') {
      content = htmlContent.trim();
      if (!content) return;
    } else if (mode === 'screenshot') {
      file = screenshotFile;
      if (!file) return;
    }

    // Set auditing state
    const seq = ++this.auditSeq;
    this.abortController = new AbortController();
    store.set({ isAuditing: true });
    this.updateAuditButtonState();

    // Notify window event for meter & peachfield
    window.dispatchEvent(new CustomEvent('cheek:audit-start'));

    try {
      const result = await postAnalyze(mode, content, file, this.abortController.signal);
      if (seq !== this.auditSeq) return; // Ignore stale response
      store.set({
        isAuditing: false,
        hasResult: true,
        currentResult: result,
      });
      window.dispatchEvent(new CustomEvent('cheek:audit-success', { detail: result }));
    } catch (err) {
      if (seq !== this.auditSeq) return; // Ignore stale error/cancel
      if (err.name === 'AbortError' && err.message !== 'timeout') {
        store.set({ isAuditing: false });
        window.dispatchEvent(new CustomEvent('cheek:audit-cancel'));
      } else {
        store.set({ isAuditing: false });
        const isRetryable = err.code === 'timeout' || err.code === 'network_error' || (err.message && (err.message.includes('too long') || err.message.includes('running') || err.message.includes('Try again')));
        this.showError(err.message || 'Audit failed. Check server status.', isRetryable ? () => this.triggerAudit() : null);
        window.dispatchEvent(new CustomEvent('cheek:audit-error', { detail: err }));
      }
    } finally {
      if (seq === this.auditSeq) {
        this.abortController = null;
        this.updateAuditButtonState();
      }
    }
  }

  // =========================================================================
  // Error Messaging (Section 10)
  // =========================================================================
  showError(msg, retryFn = null) {
    if (!this.errorBanner) return;
    this.errorText.textContent = msg;

    const existingRetry = this.errorBanner.querySelector('.btn-error-retry');
    if (existingRetry) existingRetry.remove();

    if (retryFn) {
      const retryBtn = document.createElement('button');
      retryBtn.type = 'button';
      retryBtn.className = 'btn-error-retry';
      retryBtn.style.cssText = 'margin-left: 10px; color: var(--peach); text-decoration: underline; background: none; border: none; cursor: pointer; font-weight: 600; font-size: inherit;';
      retryBtn.textContent = 'Retry';
      retryBtn.addEventListener('click', (e) => {
        e.preventDefault();
        this.clearError();
        retryFn();
      });
      this.errorBanner.appendChild(retryBtn);
    }

    this.errorBanner.hidden = false;
    this.updateAuditButtonState();
  }

  clearError() {
    if (!this.errorBanner) return;
    this.errorBanner.hidden = true;
    this.errorText.textContent = '';
    const existingRetry = this.errorBanner.querySelector('.btn-error-retry');
    if (existingRetry) existingRetry.remove();
    this.updateAuditButtonState();
  }
}
