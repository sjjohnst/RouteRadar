// Floating Layers panel logic
// Show/hide the floating panel when nav tab is toggled, and keep controls in sync.

document.addEventListener('DOMContentLoaded', () => {
    const layersTab = document.getElementById('nav-layers-tab');
    const layersPanel = document.getElementById('layers-panel');
    if (!layersTab || !layersPanel) return;

    layersTab.addEventListener('click', () => {
        const isActive = layersTab.getAttribute('aria-pressed') === 'true';
        layersTab.setAttribute('aria-pressed', String(!isActive));
        layersPanel.classList.toggle('hidden', isActive);
    });
});
