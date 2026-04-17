// Floating Tools panel logic
// Show/hide the floating panel when nav tab is toggled, and keep controls in sync.

function initToolsPanel() {
    const toolsTab = document.getElementById('nav-tools-tab');
    const toolsPanel = document.getElementById('tools-panel');
    if (!toolsTab || !toolsPanel) return;

    toolsTab.addEventListener('click', () => {
        const isActive = toolsTab.getAttribute('aria-pressed') === 'true';
        toolsTab.setAttribute('aria-pressed', String(!isActive));
        toolsPanel.classList.toggle('hidden', isActive);
    });
}

// Initialize immediately if DOM is ready, otherwise wait for DOMContentLoaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initToolsPanel);
} else {
    initToolsPanel();
}
