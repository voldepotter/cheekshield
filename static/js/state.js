/**
 * CheekShield AI — App State Store
 */

class StateStore {
  constructor() {
    this.state = {
      // Input
      mode: 'text', // 'text' | 'html' | 'screenshot'
      textContent: '',
      htmlContent: '',
      screenshotFile: null,
      screenshotPreviewUrl: null,

      // App & Analysis status
      isAuditing: false,
      modelReady: false,
      ocrReady: false,
      modelStatus: 'warming',
      modelMessage: null,
      engine: null, // 'real' | 'mock'
      demoReplay: false,

      // Active result
      hasResult: false,
      currentResult: null,

      // Filter & Sort
      filterKind: 'all', // 'all' | 'model' | 'rule'
      sortBy: 'risk', // 'risk' | 'position' | 'score'
      activeCategoryFilter: null,
    };

    this.listeners = new Set();
  }

  get() {
    return this.state;
  }

  set(updates) {
    const prev = { ...this.state };
    this.state = { ...this.state, ...updates };
    this.notify(this.state, prev);
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify(current, prev) {
    for (const listener of this.listeners) {
      try {
        listener(current, prev);
      } catch (e) {
        console.error('State subscriber error:', e);
      }
    }
  }
}

export const store = new StateStore();
