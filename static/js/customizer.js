/**
 * PrintCraft — Customizer Frontend Logic
 * Handles: product loading, view switching, design upload,
 *           render submission, status polling, result display.
 *
 * Key behaviours:
 *  - Switching product/view cancels all active polls and auto-renders if a design is already loaded
 *  - No page refresh ever required
 */

'use strict';

// ─────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────
const API_BASE = window.__API_BASE__ || '/api';
const POLL_INTERVAL_MS = 800;
const CATEGORY_EMOJIS = {
  tshirt: '👕', hoodie: '🧥', cap: '🧢',
  mug: '☕', tote: '🛍️', other: '📦',
};

/** Get CSRF token from Django's cookie — required for all POST requests */
function getCsrfToken() {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

/**
 * Safely parse a fetch Response as JSON.
 * Throws a clear error when the server returns HTML instead of JSON
 * (e.g. Django 404/500 pages in production).
 */
async function safeJson(res) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch (_) {
    // Server returned HTML (e.g. "<!DOCTYPE …") — build descriptive error
    const preview = text.substring(0, 120).replace(/\s+/g, ' ').trim();
    throw new Error(
      `Server returned ${res.status} (non-JSON). ` +
      `Check server logs. Response: "${preview}…"`
    );
  }
}

// ─────────────────────────────────────────────
// State
// ─────────────────────────────────────────────
const state = {
  products:        [],
  selectedProduct: null,
  selectedView:    null,
  designFile:      null,
  // Track every active poll interval so we can cancel them on view/product switch
  activePolls:     new Set(),
};

// ─────────────────────────────────────────────
// DOM references
// ─────────────────────────────────────────────
const $ = id => document.getElementById(id);
const productGrid       = $('product-grid');
const viewTabs          = $('view-tabs');
const canvasToolbar     = $('canvas-toolbar');
const canvasEmpty       = $('canvas-empty');
const productPreview    = $('product-preview');
const previewBaseImage  = $('preview-base-image');
const printAreaOverlay  = $('print-area-overlay');
const renderOverlay     = $('render-overlay');
const renderResultImage = $('render-result-image');
const statusBar         = $('status-bar');
const statusDot         = $('status-dot');
const statusText        = $('status-text');
const progressFill      = $('progress-fill');
const dropzone          = $('dropzone');
const fileInput         = $('design-file-input');
const designThumb       = $('design-preview-thumb');
const btnRenderAll      = $('btn-render-all');
const btnRenderCurrent  = $('btn-render-current');
const downloadArea      = $('download-area');
const btnDownload       = $('btn-download');
const downloadCardSub   = $('download-card-sub');
const allResults        = $('all-results');
const allResultsGrid    = $('all-results-grid');
const opacitySlider     = $('opacity-slider');
const opacityValue      = $('opacity-value');
const step1Pill         = $('step1-pill');
const step2Pill         = $('step2-pill');
const step3Pill         = $('step3-pill');
const btnHint           = $('btn-hint');

// ─────────────────────────────────────────────
// Step Indicator
// ─────────────────────────────────────────────
function updateSteps() {
  const hasProduct = !!state.selectedProduct;
  const hasDesign  = !!state.designFile;

  step1Pill.className = 'step-pill ' + (hasProduct ? 'step-done' : 'step-active');

  if (!hasProduct) {
    step2Pill.className = 'step-pill';
    dropzone.classList.remove('needs-upload');
  } else if (!hasDesign) {
    step2Pill.className = 'step-pill step-active';
    dropzone.classList.add('needs-upload');
  } else {
    step2Pill.className = 'step-pill step-done';
    dropzone.classList.remove('needs-upload');
  }

  step3Pill.className = 'step-pill ' + (hasDesign ? 'step-active' : '');
  if (btnHint) btnHint.style.display = (hasProduct && !hasDesign) ? 'block' : 'none';
}

// ─────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  updateSteps();      // set initial state
  loadProducts();
  setupDropzone();
  setupButtons();
  setupOpacity();
});

// ─────────────────────────────────────────────
// Load Products
// ─────────────────────────────────────────────
async function loadProducts() {
  try {
    const res = await fetch(`${API_BASE}/products/`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.products = await safeJson(res);
    renderProductGrid();
  } catch (err) {
    productGrid.innerHTML = `<p style="color:var(--c-danger);padding:1rem;font-size:.85rem;">
      Failed to load products. Make sure the Django server is running.<br>
      <small>${err.message}</small>
    </p>`;
  }
}

function renderProductGrid() {
  if (!state.products.length) {
    productGrid.innerHTML = `
      <div style="padding:1.5rem;text-align:center;color:var(--c-text-muted);font-size:.85rem;">
        No products yet. <a href="/admin/products/product/add/" style="color:var(--c-primary-h);">Add one in Admin →</a>
      </div>`;
    return;
  }

  productGrid.innerHTML = '';
  state.products.forEach(product => {
    const card = document.createElement('div');
    card.className = 'product-card';
    card.setAttribute('role', 'listitem');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-label', product.name);
    card.dataset.productId = product.id;

    const firstView = product.views?.[0];
    const thumbHTML = firstView?.base_image_url
      ? `<img class="product-card-thumb" src="${firstView.base_image_url}" alt="${product.name}" loading="lazy" />`
      : `<div class="product-card-thumb-placeholder">${CATEGORY_EMOJIS[product.category] || '📦'}</div>`;

    const viewCount = product.views?.length || 0;
    card.innerHTML = `
      ${thumbHTML}
      <div class="product-card-info">
        <div class="product-card-name">${product.name}</div>
        <div class="product-card-cat">${product.category_display || product.category}</div>
      </div>
      <div class="product-card-badge">${viewCount} view${viewCount !== 1 ? 's' : ''}</div>
    `;

    card.addEventListener('click', () => selectProduct(product));
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') selectProduct(product); });
    productGrid.appendChild(card);
  });
}

// ─────────────────────────────────────────────
// Select Product
// ─────────────────────────────────────────────
function selectProduct(product) {
  // Don't re-select the same product (avoid unnecessary re-render flicker)
  if (state.selectedProduct?.id === product.id) return;

  cancelAllPolls();
  wipeCanavsResult();

  state.selectedProduct = product;
  state.selectedView    = null;

  // Highlight active card
  document.querySelectorAll('.product-card').forEach(c => c.classList.remove('active'));
  const card = productGrid.querySelector(`[data-product-id="${product.id}"]`);
  if (card) card.classList.add('active');

  renderViewTabs(product.views || []);

  if (product.views?.length) {
    selectView(product.views[0]);
  }

  updateRenderButtons();
  updateSteps();
}

function renderViewTabs(views) {
  viewTabs.innerHTML = '';
  views.forEach((view, i) => {
    const tab = document.createElement('button');
    tab.className = 'view-tab' + (i === 0 ? ' active' : '');
    tab.textContent = view.view_label.charAt(0).toUpperCase() + view.view_label.slice(1);
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-selected', i === 0 ? 'true' : 'false');
    tab.dataset.viewId = view.id;

    tab.addEventListener('click', () => {
      if (state.selectedView?.id === view.id) return; // already selected
      document.querySelectorAll('.view-tab').forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
      });
      tab.classList.add('active');
      tab.setAttribute('aria-selected', 'true');
      selectView(view);
    });

    viewTabs.appendChild(tab);
  });

  canvasToolbar.style.display = 'flex';
}

// ─────────────────────────────────────────────
// Select View — cancels active renders, auto-renders if design ready
// ─────────────────────────────────────────────
function selectView(view) {
  cancelAllPolls();
  wipeCanavsResult();

  state.selectedView = view;

  canvasEmpty.style.display = 'none';
  productPreview.style.display = 'block';

  // Use decode() instead of onload — works whether image is cached or not
  previewBaseImage.src = view.base_image_url || '';
  previewBaseImage.decode()
    .catch(() => {}) // ignore decode errors (e.g. placeholder images)
    .finally(() => {
      positionPrintAreaOverlay(view);
      // Auto-render if a design is already uploaded — no button click needed
      if (state.designFile) {
        autoRenderCurrentView();
      }
    });

  updateRenderButtons();
}

function positionPrintAreaOverlay(view) {
  if (!previewBaseImage.naturalWidth) return;
  const scaleX = previewBaseImage.offsetWidth  / previewBaseImage.naturalWidth;
  const scaleY = previewBaseImage.offsetHeight / previewBaseImage.naturalHeight;

  printAreaOverlay.style.left   = `${view.print_area_x * scaleX}px`;
  printAreaOverlay.style.top    = `${view.print_area_y * scaleY}px`;
  printAreaOverlay.style.width  = `${view.print_area_w * scaleX}px`;
  printAreaOverlay.style.height = `${view.print_area_h * scaleY}px`;
  printAreaOverlay.classList.remove('hidden');
}

// ─────────────────────────────────────────────
// Dropzone / File input
// ─────────────────────────────────────────────
function setupDropzone() {
  dropzone.addEventListener('click', () => fileInput.click());
  dropzone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });

  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) handleDesignFile(fileInput.files[0]);
  });

  dropzone.addEventListener('dragover', e => {
    e.preventDefault(); dropzone.classList.add('drag-over');
  });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
  dropzone.addEventListener('drop', e => {
    e.preventDefault(); dropzone.classList.remove('drag-over');
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith('image/')) handleDesignFile(file);
  });
}

function handleDesignFile(file) {
  state.designFile = file;

  const url = URL.createObjectURL(file);
  designThumb.src = url;
  designThumb.style.display = 'block';
  $('dropzone-icon').style.display = 'none';

  updateRenderButtons();
  updateSteps();

  // If a view is already selected, auto-render immediately
  if (state.selectedView) {
    // Small delay so the thumb renders visually before we start the spinner
    setTimeout(() => autoRenderCurrentView(), 80);
  }
}

// ─────────────────────────────────────────────
// Opacity Slider — re-renders on change
// ─────────────────────────────────────────────
function setupOpacity() {
  let debounceTimer = null;
  opacitySlider.addEventListener('input', () => {
    opacityValue.textContent = `${opacitySlider.value}%`;
    // Debounce re-render on opacity change (wait 600ms after user stops sliding)
    clearTimeout(debounceTimer);
    if (state.designFile && state.selectedView) {
      debounceTimer = setTimeout(() => autoRenderCurrentView(), 600);
    }
  });
}

// ─────────────────────────────────────────────
// Buttons
// ─────────────────────────────────────────────
function setupButtons() {
  btnRenderCurrent.addEventListener('click', () => {
    // Manual click always triggers a fresh render regardless of auto-render state
    cancelAllPolls();
    wipeCanavsResult();
    renderCurrentView();
  });
  btnRenderAll.addEventListener('click', renderAllViews);
}

function updateRenderButtons() {
  const hasView    = !!state.selectedView;
  const hasDesign  = !!state.designFile;
  const hasProduct = !!state.selectedProduct;

  btnRenderCurrent.disabled = !(hasView && hasDesign);
  btnRenderAll.disabled     = !(hasProduct && hasDesign);
}

// ─────────────────────────────────────────────
// Auto-render (silent, no user action required)
// ─────────────────────────────────────────────
function autoRenderCurrentView() {
  cancelAllPolls();
  wipeCanavsResult();
  renderCurrentView();
}

// ─────────────────────────────────────────────
// Render — Current View
// ─────────────────────────────────────────────
async function renderCurrentView() {
  if (!state.designFile || !state.selectedView) return;

  // Snapshot the view at the moment submission starts
  const targetViewId    = state.selectedView.id;
  const targetViewLabel = state.selectedView.view_label;

  setStatus('processing', 'Submitting render…', 10);
  printAreaOverlay.classList.add('hidden');

  const formData = new FormData();
  formData.append('product_view_id', targetViewId);
  formData.append('design', state.designFile);
  formData.append('design_opacity', (parseInt(opacitySlider.value) / 100).toFixed(2));

  try {
    const res  = await fetch(`${API_BASE}/render/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken() },
      body: formData,
    });
    const data = await safeJson(res);

    // If the user switched views while the request was in-flight, discard silently
    if (state.selectedView?.id !== targetViewId) return;

    if (data.cached) {
      setStatus('done', 'Render complete! (cached)', 100);
      showRenderResult(data.result_image_url || data.cached_url, `${targetViewLabel} (cached)`);
      return;
    }

    if (data.job_id) {
      setStatus('processing', 'Rendering in progress…', 30);
      pollJobStatus(data.job_id, targetViewId, targetViewLabel);
    } else {
      setStatus('failed', data.error || 'Submission failed. Check that the product view has been analyzed.', 0);
      printAreaOverlay.classList.remove('hidden');
    }
  } catch (err) {
    if (state.selectedView?.id === targetViewId) {
      setStatus('failed', `Network error: ${err.message}`, 0);
      printAreaOverlay.classList.remove('hidden');
    }
  }
}

// ─────────────────────────────────────────────
// Render — All Views
// ─────────────────────────────────────────────
async function renderAllViews() {
  if (!state.designFile || !state.selectedProduct) return;

  cancelAllPolls();
  wipeCanavsResult();

  const targetProduct = state.selectedProduct;

  allResults.style.display = 'block';
  allResultsGrid.innerHTML = '';
  downloadArea.style.display = 'none';

  const views = targetProduct.views || [];
  views.forEach(v => {
    const card = document.createElement('div');
    card.className = 'result-thumb-card';
    card.id = `result-card-${v.id}`;
    card.innerHTML = `<div class="result-thumb-loading">⏳ ${v.view_label}</div>`;
    allResultsGrid.appendChild(card);
  });

  setStatus('processing', `Rendering ${views.length} view${views.length > 1 ? 's' : ''}…`, 15);

  const formData = new FormData();
  formData.append('product_id', targetProduct.id);
  formData.append('design', state.designFile);
  formData.append('design_opacity', (parseInt(opacitySlider.value) / 100).toFixed(2));

  try {
    const res  = await fetch(`${API_BASE}/render/all/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken() },
      body: formData,
    });
    const data = await safeJson(res);

    if (state.selectedProduct?.id !== targetProduct.id) return;

    if (!data.jobs) {
      setStatus('failed', data.error || 'Render failed.', 0);
      return;
    }

    let completed = 0;
    const total   = data.jobs.length;

    data.jobs.forEach(({ job_id, view_label }) => {
      // Find view id by label for card lookup
      const matchedView = targetProduct.views.find(v => v.view_label === view_label);
      const cardId = matchedView ? `result-card-${matchedView.id}` : `result-card-${view_label}`;

      const intervalId = setInterval(async () => {
        // Cancel if product changed
        if (state.selectedProduct?.id !== targetProduct.id) {
          clearInterval(intervalId);
          state.activePolls.delete(intervalId);
          return;
        }
        try {
          const jRes  = await fetch(`${API_BASE}/render/${job_id}/status/`);
          const jData = await safeJson(jRes);

          if (jData.status === 'done') {
            clearInterval(intervalId);
            state.activePolls.delete(intervalId);
            completed++;
            const progress = Math.round((completed / total) * 100);

            if (completed < total) {
              setStatus('processing', `${completed}/${total} views rendered`, progress);
            } else {
              setStatus('done', `All ${total} view${total > 1 ? 's' : ''} rendered!`, 100);
            }

            const card = $(cardId);
            if (card && jData.result_image_url) {
              card.innerHTML = `
                <img src="${jData.result_image_url}" alt="${view_label} render" loading="lazy" />
                <div class="result-thumb-label">${view_label}</div>
              `;
            }

          } else if (jData.status === 'failed') {
            clearInterval(intervalId);
            state.activePolls.delete(intervalId);
            completed++;
            const card = $(cardId);
            if (card) card.innerHTML = `<div class="result-thumb-loading" style="color:var(--c-danger)">Failed</div>`;
          }
        } catch (_) { /* network hiccup — keep polling */ }
      }, POLL_INTERVAL_MS);

      state.activePolls.add(intervalId);
    });

  } catch (err) {
    setStatus('failed', `Error: ${err.message}`, 0);
  }
}

// ─────────────────────────────────────────────
// Job Status Polling — tracks interval in state
// ─────────────────────────────────────────────
function pollJobStatus(jobId, targetViewId, targetViewLabel) {
  let progress = 30;

  const intervalId = setInterval(async () => {
    // If the user switched view, stop this poll silently
    if (state.selectedView?.id !== targetViewId) {
      clearInterval(intervalId);
      state.activePolls.delete(intervalId);
      return;
    }
    try {
      const res  = await fetch(`${API_BASE}/render/${jobId}/status/`);
      const data = await safeJson(res);

      if (data.status === 'done') {
        clearInterval(intervalId);
        state.activePolls.delete(intervalId);
        setStatus('done', 'Render complete!', 100);
        if (data.result_image_url) {
          showRenderResult(data.result_image_url, targetViewLabel);
        }
      } else if (data.status === 'failed') {
        clearInterval(intervalId);
        state.activePolls.delete(intervalId);
        const msg = data.error_message || 'Render failed.';
        setStatus('failed', msg, 0);
        printAreaOverlay.classList.remove('hidden');
      } else {
        progress = Math.min(progress + 7, 90);
        setStatus('processing', 'Rendering…', progress);
      }
    } catch (_) { /* keep polling on network hiccup */ }
  }, POLL_INTERVAL_MS);

  state.activePolls.add(intervalId);
}

// ─────────────────────────────────────────────
// Display Render Result
// ─────────────────────────────────────────────
function showRenderResult(imageUrl, label) {
  renderResultImage.src = imageUrl;
  renderOverlay.style.display = 'block';
  printAreaOverlay.classList.add('hidden');

  downloadArea.style.display = 'block';
  btnDownload.href = imageUrl;
  downloadCardSub.textContent = label;
}

// ─────────────────────────────────────────────
// Status Bar Helpers  (was accidentally removed in refactor)
// ─────────────────────────────────────────────
function setStatus(type, text, progress) {
  statusBar.style.display = 'block';
  statusText.textContent  = text;
  progressFill.style.width = `${progress}%`;

  statusDot.className = 'status-dot';
  if (type === 'done')   statusDot.classList.add('done');
  if (type === 'failed') statusDot.classList.add('failed');
}

// ─────────────────────────────────────────────
// Cancel all active polls (view/product switch)
// ─────────────────────────────────────────────
function cancelAllPolls() {
  state.activePolls.forEach(id => clearInterval(id));
  state.activePolls.clear();
}

// ─────────────────────────────────────────────
// Wipe canvas render state (no page refresh needed)
// ─────────────────────────────────────────────
function wipeCanavsResult() {
  renderOverlay.style.display = 'none';
  renderResultImage.src = '';       // clear old image so it doesn't flash
  statusBar.style.display = 'none';
  downloadArea.style.display = 'none';
  allResults.style.display = 'none';
  allResultsGrid.innerHTML = '';
  progressFill.style.width = '0%';
}

// ─────────────────────────────────────────────
// Reposition overlay on window resize
// ─────────────────────────────────────────────
window.addEventListener('resize', () => {
  if (state.selectedView) positionPrintAreaOverlay(state.selectedView);
});
