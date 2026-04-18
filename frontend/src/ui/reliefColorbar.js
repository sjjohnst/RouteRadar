/**
 * src/ui/reliefColorbar.js
 *
 * Draws a vertical colorbar for the relief layer using a Canvas element.
 * The gradient is an approximation of the matplotlib "cividis" colormap.
 *
 * Public API:
 *   initReliefColorbar()          – renders the initial bar and attaches to DOM
 *   updateReliefColorbar(vmin, vmax) – refreshes labels when bounds change
 *   showReliefColorbar(visible)   – shows/hides the overlay
 */

// Cividis palette sampled at 11 stops from matplotlib.
// Format: [r, g, b] in 0–255.
const CIVIDIS_STOPS = [
    [  0,  34,  78],
    [  0,  57, 111],
    [ 35,  79, 124],
    [ 73, 101, 132],
    [109, 122, 139],
    [146, 143, 145],
    [181, 163, 139],
    [210, 185, 121],
    [234, 209,  92],
    [249, 234,  52],
    [253, 255,  55],
];

/**
 * Paint the cividis gradient onto the canvas from top (max) to bottom (min).
 * @param {HTMLCanvasElement} canvas
 */
function paintCividis(canvas) {
    const ctx = canvas.getContext('2d');
    const h = canvas.height;
    const w = canvas.width;
    const radius = Math.min(w, h) / 2;

    // Build a linear gradient top-to-bottom (top = high value = warm end)
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    const n = CIVIDIS_STOPS.length;
    CIVIDIS_STOPS.slice().reverse().forEach(([r, g, b], i) => {
        grad.addColorStop(i / (n - 1), `rgb(${r},${g},${b})`);
    });

    // Draw rounded rectangle (vertical capsule)
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(radius, 0);
    ctx.lineTo(w - radius, 0);
    ctx.arcTo(w, 0, w, radius, radius);
    ctx.lineTo(w, h - radius);
    ctx.arcTo(w, h, w - radius, h, radius);
    ctx.lineTo(radius, h);
    ctx.arcTo(0, h, 0, h - radius, radius);
    ctx.lineTo(0, radius);
    ctx.arcTo(0, 0, radius, 0, radius);
    ctx.closePath();
    ctx.clip();
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);
    ctx.restore();
}

/** Format a number nicely for a label. */
function fmt(v) {
    return Number.isFinite(v) ? v.toFixed(1) + ' m' : '—';
}

/**
 * Initialise the colorbar and return an update handle.
 * Must be called after the DOM is ready.
 */
export function initReliefColorbar(vmin, vmax) {
    const container = document.getElementById('relief-colorbar');
    const canvas    = document.getElementById('relief-colorbar-canvas');
    const labelMin  = document.getElementById('relief-colorbar-min');
    const labelMax  = document.getElementById('relief-colorbar-max');

    if (!container || !canvas || !labelMin || !labelMax) return;

    paintCividis(canvas);
    labelMin.textContent = fmt(vmin);
    labelMax.textContent = fmt(vmax);
}

export function updateReliefColorbar(vmin, vmax) {
    const labelMin = document.getElementById('relief-colorbar-min');
    const labelMax = document.getElementById('relief-colorbar-max');
    if (labelMin) labelMin.textContent = fmt(vmin);
    if (labelMax) labelMax.textContent = fmt(vmax);
}

export function showReliefColorbar(visible) {
    const container = document.getElementById('relief-colorbar');
    if (!container) return;
    container.classList.toggle('hidden', !visible);
}
