export function setupToolkitToggle() {
    const layout = document.getElementById('layout');
    const navToggle = document.getElementById('toolkit-toggle-nav');

    if (!layout || !navToggle) {
        return;
    }

    const updateLabel = () => {
        const collapsed = layout.classList.contains('toolkit-collapsed');
        navToggle.textContent = collapsed ? 'Show tools' : 'Hide tools';
    };

    navToggle.addEventListener('click', () => {
        layout.classList.toggle('toolkit-collapsed');
        updateLabel();
    });

    // Ensure initial label matches initial state
    updateLabel();
}
