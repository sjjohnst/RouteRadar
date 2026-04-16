/**
 * Help Guide Content for RouteRadar
 * This module populates the help popup with guide content
 */

export function initHelpGuide() {
    const helpContent = document.getElementById('help-content');
    
    if (!helpContent) return;

    helpContent.innerHTML = `
        <div class="help-guide">
            <div class="help-section">
                <h3>Layers</h3>
                <p>Toggle map layers on/off:</p>
                <ul>
                    <li><strong>Public Land</strong> - View public land areas</li>
                    <li><strong>Height Estimate</strong> - Terrain elevation visualization</li>
                </ul>
            </div>

            <div class="help-section">
                <h3>Tools</h3>
                <p>Use interactive tools to analyze the map:</p>
                <ul>
                    <li><strong>Info</strong> - Click on map features for details</li>
                    <li><strong>Marker</strong> - Place markers on the map</li>
                    <li><strong>Measure</strong> - Measure distances</li>
                </ul>
            </div>

            <div class="help-section">
                <h3>Tips</h3>
                <ul>
                    <li>Adjust layer opacity with sliders</li>
                    <li>Use the scale bar to gauge distances</li>
                    <li>Zoom and pan to explore areas</li>
                </ul>
            </div>
        </div>
    `;
}
