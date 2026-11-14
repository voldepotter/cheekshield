/**
 * CheekShield AI — API Client (Section 5.2, Section 7 Phase 7)
 *
 * All frontend requests go through these functions.
 * Fallback to saved/canned results occurs ONLY when DEMO_REPLAY=1 is on and the engine failed.
 */

import { CANNED_DECEPTIVE, CANNED_CLEAN } from './canned_results.js';
import { store } from './state.js';

export async function fetchHealth() {
  const res = await fetch('/api/health');
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return await res.json();
}

export async function fetchModelInfo() {
  const res = await fetch('/api/model');
  if (!res.ok) {
    if (res.status === 404 || res.status === 503) {
      return null;
    }
    throw new Error(`Model info failed: ${res.status}`);
  }
  return await res.json();
}

export async function fetchSamples() {
  try {
    const res = await fetch('/api/samples');
    if (!res.ok) throw new Error(`Fetch samples failed: ${res.status}`);
    return await res.json();
  } catch (err) {
    // Return null to trigger InputController fallback
    return null;
  }
}

export async function postAnalyze(mode, content, file = null, userSignal = null) {
  // Setup 90s timeout (Section 10)
  const timeoutMs = 90000;
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => {
    timeoutController.abort(new Error('timeout'));
  }, timeoutMs);

  // Combine signals
  let combinedSignal = timeoutController.signal;
  if (userSignal) {
    userSignal.addEventListener('abort', () => {
      clearTimeout(timeoutId);
      timeoutController.abort(userSignal.reason);
    });
    if (userSignal.aborted) {
      clearTimeout(timeoutId);
      timeoutController.abort(userSignal.reason);
    }
  }

  try {
    let options = { method: 'POST', signal: combinedSignal };

    if (mode === 'screenshot') {
      const formData = new FormData();
      formData.append('mode', 'screenshot');
      if (file) formData.append('file', file);
      options.body = formData;
    } else {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify({ mode, content });
    }

    const res = await fetch('/api/analyze', options);
    clearTimeout(timeoutId);
    const data = await res.json();

    if (!res.ok) {
      const message = data?.error?.message || `Analysis failed (${res.status})`;
      const code = data?.error?.code || 'error';
      const err = new Error(message);
      err.code = code;
      throw err;
    }

    return data;
  } catch (err) {
    clearTimeout(timeoutId);

    // Timeout detection
    if (combinedSignal.aborted && combinedSignal.reason?.message === 'timeout') {
      const timeoutErr = new Error('The audit took too long. Try a smaller input.');
      timeoutErr.code = 'timeout';
      throw timeoutErr;
    }

    // User cancellation
    if (userSignal?.aborted) {
      throw userSignal.reason || new Error('Aborted');
    }

    // Demo safety net (Section 7 Phase 7 point 6, Task 3)
    // Saved/canned results may be shown ONLY when DEMO_REPLAY=1 option is on
    // and the engine failed, with a clearly visible "Saved result" tag.
    const urlParams = new URLSearchParams(window.location.search);
    const isDemoReplay = (store.get().demoReplay === true) || (urlParams.get('demo_replay') === '1');
    if (isDemoReplay) {
      const isDeceptive = Boolean(
        content && (
          content.toLowerCase().includes('hurry') ||
          content.toLowerCase().includes('left in stock') ||
          content.toLowerCase().includes('people are viewing') ||
          content.toLowerCase().includes('order protection') ||
          content.toLowerCase().includes('auto-renews') ||
          content.toLowerCase().includes('keep my plan')
        )
      );
      const canned = JSON.parse(JSON.stringify(isDeceptive ? CANNED_DECEPTIVE : CANNED_CLEAN));
      canned._isSavedResult = true;
      return canned;
    }

    // Network unreachable
    if (err instanceof TypeError || (err.message && err.message.toLowerCase().includes('fetch'))) {
      const netErr = new Error('Cannot reach the server. Check that it is running.');
      netErr.code = 'network_error';
      throw netErr;
    }

    throw err;
  }
}
