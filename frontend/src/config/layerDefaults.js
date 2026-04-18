export const layerDefaults = {
  // HRDEM WMS tiles removed: DTM, slope and hillshade were removed.
  quebecPublicLand: {
    id: 'quebec-public-land',
    layerId: 'quebec-public-land-layer',
    visible: true,
    opacity: 0.70,
  },
  relief: {
    id: 'hrdem-relief',
    layerId: 'hrdem-relief-layer',
    visible: false,
    opacity: 0.30,
    colormap: 'cividis',
    // Physical display range in metres — converted to DN when building the tile URL
    vminMetres: 0.0,
    vmaxMetres: 3.5,
  },
};
