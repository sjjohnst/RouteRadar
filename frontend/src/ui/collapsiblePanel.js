// A nav tab that shows and hides its floating panel.
// aria-pressed on the tab is the source of truth for whether the panel is open.

/**
 * @param {string} tabId    id of the nav tab button
 * @param {string} panelId  id of the panel it opens
 */
export function initCollapsiblePanel(tabId, panelId) {
    const tab = document.getElementById(tabId);
    const panel = document.getElementById(panelId);
    if (!tab || !panel) return;

    tab.addEventListener('click', () => {
        const isOpen = tab.getAttribute('aria-pressed') === 'true';
        tab.setAttribute('aria-pressed', String(!isOpen));
        panel.classList.toggle('hidden', isOpen);
    });
}
