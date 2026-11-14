# CheekShield AI — Decisions Log

Each line records a choice made during build where the spec was ambiguous or
a fallback was needed.

| # | Decision | Reason |
|---|----------|--------|
| 1 | Hero line: "Paste a page. Cheeko checks its cheek." | Matches the playful peach personality best. |
| 2 | Fonts: using fallback stacks (Georgia/system-ui/monospace) until WOFF2 files are placed in `static/assets/fonts/`. Fraunces → `static/assets/fonts/Fraunces-Variable.woff2`, Figtree → `Figtree-Variable.woff2`, DM Mono → `DMMono-Regular.woff2` + `DMMono-Medium.woff2`. | Font files cannot be downloaded in this build environment. |
| 3 | Pre-filter stubs are included in findings with `kind: "checked"` and counted toward `checked_fine`, never displayed as flags. | Section 4 point 2 says "count them as checked only". |
| 4 | Unknown risk strings default to `Low Risk` (rank 1) as a safe fallback. | Better to over-flag than silently hide. |
| 5 | `normalize_summary` recomputes flagged/checked/routine counts from normalized findings rather than trusting engine totals. | Engine counts may include pre-filter stubs differently. |
| 6 | Meter spring uses stiffness=4.0, damping=3.5 for a snappy fill with slight overshoot. Slosh amplitude spikes to 14-24 on new result, decays over 2s. | Feels "juicy" without being distracting; matches the 600ms spring spec. |
| 7 | Loading messages cycle every 2.2s (4 messages). Number area goes blank during analyzing to make room for the message in the band line. | Keeps the analyzing state lively without jarring layout shifts. |
| 8 | Bubbles: 6 pooled circles, spawn probabilistically, drift upward with sine wobble, fade near surface. Streaks: 5 static vertical lines at 12% opacity. | Subtle juice details that reward close inspection without impacting perf. |
| 9 | Clean result (exposure 0%) triggers `setClean()` state instead of `setResult()`. Shows leaf-green tick, solid outline, "Fresh" band. | Spec says clean gets its own state with the leaf tick (Section 7 Phase 3 states table). |
| 10 | Receipt tally shows every category in the registry plus unknown finding categories. Categories with 0 flags receive class `dimmed`. | Section 6.7 and 6.8 require zero-count categories to show as checked. |
| 11 | Attributed tokens are highlighted using safe text node splitting without `innerHTML` to prevent XSS. Alpha scales with delta_p weight up to 0.85. | Meets strict security guidelines (Section 2 Rule I) while keeping tooltips interactive. |
| 12 | Rule findings display attributions as dashed chips with raw rule weight, never percentages. | Adheres to honesty rule: heuristics are not probabilities. |
| 13 | Checked-fine items paginate in batches of 50 inside the collapsed disclosure. | Avoids DOM lag on inputs with hundreds of benign elements (Section 7 Phase 4). |
| 14 | Two-way sync between screenshot bounding boxes and finding rows via hover/click listeners. | Section 7 Phase 4 requirement for seamless visual audit correlation. |
| 15 | `_read_meta` uses `utf-8-sig` encoding so both standard UTF-8 and Windows BOM-encoded `meta.json` files parse cleanly. | Prevents crash when editors (e.g., PowerShell/Notepad) save with UTF-8 BOM. |
| 16 | `get_model_info` checks for hot reload under lock before returning info, guaranteeing `/api/model` reflects updated weights or meta.json immediately without waiting for an audit. | Enables instant hot-reload verification in Phase 5 swap drill. |
| 17 | Model metrics grid displays all 5 headline metrics: Macro F1, Dark-vs-Benign Precision, Recall, F1, and Dark Threshold. | Section 7 Phase 5 explicitly requests dark-vs-benign precision, recall, and F1. |
| 18 | Model status chip shows "Model missing" with exact remediation message when model directory is unpopulated outside mock mode. | Adheres to Section 10 table error handling specification. |
| 19 | JSON export provides a toggle to include or omit base64 annotated image data, keeping files under 5KB when image is omitted. | Section 7 Phase 6 explicitly requests the option to include or exclude annotated image. |
| 20 | PDF export uses pure `print.css` with `@media print`, expanding all collapsibles and hiding interactive controls without heavy JS PDF dependencies. | Fulfills zero-frontend-dependency architectural rule (Section 2 Rule E). |
| 21 | Ethical comparison mocks for Urgency, Preselected Choice, and Misdirection use static templates with zero user data rendered inside. | Satisfies stretch goal (Section 7 Phase 6) while enforcing anti-XSS safety. |
| 22 | "Copy summary" action copies a clean structured markdown/plain text overview to the clipboard with one click. | Optional convenience feature from Section 7 Phase 6.4. |
| 23 | Enforce minimum 44×44px touch targets across tabs, buttons, links, inputs, and controls via `min-height: 44px; display: inline-flex; align-items: center;`. | Section 7 Phase 7 responsive & WCAG accessibility requirement. |
| 24 | Enforce `font-size: 16px` across all textareas (including monospace HTML box) to prevent iOS Safari auto-zooming. | Section 7 Phase 7 explicit requirement. |
| 25 | Replace hardcoded mobile widths (390px) with fluid 100% viewport width, stack evidence row left rail horizontally above findings, and render the screenshot viewer full-bleed at $\le 759$px. | Section 8 responsive layout rules; eliminates horizontal scrolling at 360px and 390px. |
| 26 | Handle all Section 10 edge-cases including OCR unavailable banner on screenshot tab, 90s request timeout with retry button, network failure actionable error banner, and `summary.status == "no_content"` empty screen. | Section 10 table full specification adherence. |
| 27 | Implement demo keyboard shortcut (`Alt+D` / `Ctrl+Shift+D`) and `?demo=1` mounting a floating demo toolbar; enable `DEMO_REPLAY=1` safety net serving labeled saved results (`_isSavedResult = True`) on backend engine failure. | Section 7 Phase 7 point 6 and Section 12 demo script requirement. |
| 28 | Browser profiles and scratch files are created strictly in OS temp (`tempfile.mkdtemp` / `TemporaryDirectory`) with finally-block exit and retry cleanup; never under project root. | Task 1 junk prevention and anti-pollution rule. |
| 29 | `.gitignore` hardened to cover model weights (`*.safetensors`, `*.bin`, `*.pt`, `*.onnx`, `*.ckpt`), temp directories (`temp*chrome*/`, `temp_p7_*/`, `scratch/`), logs, and editor configs, while preserving `meta.json` and `.gitkeep`. | Task 2 repository hygiene and git safety. |
| 30 | Canned results restricted strictly to `DEMO_REPLAY=1` on engine failure with visible "Saved result" banner and receipt tag; eliminated silent fallbacks in `fetchModelInfo` and `fetchHealth`. | Task 3 canned results audit and honesty rule. |
| 31 | `MODEL_DIR` defaults to absolute path from `config.py`; `CHEEK_MOCK` defaults to OFF with header chip displaying "Mock engine" when active and `/api/health` returning `"engine": "real"|"mock"`. | Task 4 model integration transparency and fail-fast startup. |
| 32 | Preflight diagnostic tool (`scripts/preflight.py`) provides PASS/FAIL checklist for engine exports, model bundle, Python packages, EasyOCR weights, and port availability without loading full model. | Task 4 preflight diagnostic command requirement. |
| 33 | Tests requiring the real model (`@pytest.mark.real_model` or `CHEEK_MOCK=0`) automatically skip with clear reason when `outputs/model/` is empty instead of crashing. | Task 4 test skip behavior requirement. |
| 34 | Change 1: Reduced top spacing by ~40% (header 59px, gap 32px, heading 91px, heading-slab 20px) bringing Audit button well above fold at 1440x900. | Fulfills compact viewport requirement without cramped appearance. |
| 35 | Change 2: Updated hero tagline verbatim to "Cheeko checks the softspots." across HTML and UI. | Matches requested copy exactly with single word and period. |
| 36 | Change 3: Background peaches opacity raised to GRID_ALPHA=0.14 and FLOATER_ALPHA=0.24 via top-level constants. | Ensures floating peaches are clearly visible while remaining gentle background. |
| 37 | Change 4: Fixed percentage data flow bug by resetting displayNumber in clean/idle/error states, differentiating screenshot OCR mock findings, adding clean/flag guards, no-store headers, and request sequence tracking. | Root cause was multi-layered: meter animation loop overwriting clean 0 with stale displayNumber, lack of request sequencing, and mock engine always returning deceptive findings for screenshots. |
| 38 | Change 5: Removed "Known limitations" section from page, JS renderer, and CSS while preserving API field and config. | Keeps UI clean and focused on confusion matrix metrics while preserving backend contract. |
| 39 | Change 6: Redesigned receipt card with 6px peach band, Fraunces sentence-case title, Item/Qty/Risk tabular layout with risk notches, contrast-compliant zero rows, double-rule total with 8px bar gauge, static disclaimer stamp, Figtree buttons, custom 18px checkbox, and native CSS clip-path zigzag. | Transforms receipt into integrated, thematic component matching the orange/white/black visual language. |
| 40 | Change 7: Formatted dark threshold to exactly two decimal places using formatThreshold helper. | Prevents unrounded floating-point values from displaying in the model evaluation panel. |
