/**
 * Help Guide Content for RouteRadar
 * This module populates the help popup with guide content
 */

export function initHelpGuide() {
    const helpContent = document.getElementById('help-content');
    
    if (!helpContent) return;

    helpContent.innerHTML = `
        <div class="help-guide" style="max-height: 75vh; overflow-y: auto; padding-bottom: 1.5em;">
            <div class="help-section">
                <h3>Navigation</h3>
                <ul>
                    <li><strong>Pan:</strong> Click and drag the map with your mouse to move around.</li>
                    <li><strong>Zoom:</strong> Use your mouse wheel or the +/− buttons to zoom in and out.</li>
                </ul>
            </div>

            <div class="help-section">
                <h3>Layers</h3>
                <ul>
                    <li><strong>Base Map:</strong> Aerial imagery from Gouvernement du Québec. <a href="https://mrnf.gouv.qc.ca/repertoire-geographique/vue-aerienne-quebec-imagerie-continue/" target="_blank" rel="noopener">View source</a></li>
                    <li><strong>Plans d'affectation du territoire public (Public Land):</strong> Québec government dataset of public land designations. <a href="https://www.donneesquebec.ca/recherche/dataset/plans-d-affectation-du-territoire-public" target="_blank" rel="noopener">View source</a></li>
                    <li><strong>Height Estimate (Relief):</strong> Elevation difference (relief) calculated from <a href="https://open.canada.ca/data/en/dataset/957782bf-847c-4644-a757-e383c0057995" target="_blank" rel="noopener">HRDEM 1m resolution data</a>.</li>
                </ul>
            </div>

            <div class="help-section">
                <h3>Layer Settings</h3>
                <ul>
                    <li>Change <strong>opacity</strong> of each layer using the sliders.</li>
                    <li>For Height Estimate, you can <strong>rescale</strong> the relief color range by setting new min/max values and clicking Apply.</li>
                </ul>
            </div>

            <div class="help-section">
                <h3>Tools</h3>
                <ul>
                    <li><strong>Drop Marker:</strong> Place a marker anywhere on the map.</li>
                    <li><strong>Measure Distance:</strong> Click to start, drag and release to measure straight-line distance.</li>
                    <li><strong>Query Info:</strong> Click on public land areas to view details about the selected parcel.</li>
                </ul>
            </div>
        </div>
    `;
}
