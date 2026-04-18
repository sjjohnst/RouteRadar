// Floating Layers panel logic
// Show/hide the floating panel when nav tab is toggled, and keep controls in sync.

function initLayersPanel() {
    const layersTab = document.getElementById('nav-layers-tab');
    const layersPanel = document.getElementById('layers-panel');
    if (!layersTab || !layersPanel) return;

    layersTab.addEventListener('click', () => {
        const isActive = layersTab.getAttribute('aria-pressed') === 'true';
        layersTab.setAttribute('aria-pressed', String(!isActive));
        layersPanel.classList.toggle('hidden', isActive);
    });
}

// Initialize immediately if DOM is ready, otherwise wait for DOMContentLoaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLayersPanel);
} else {
    initLayersPanel();
}
