export const layerDefaults = {
  dtm: {
    id: 'hrdem-wms-dtm',
    layerId: 'hrdem-wms-dtm-layer',
    visible: false,
    opacity: 0.8,
    colormap: '', // None (default)
    rescale: '0,500',
    style: 'default',
  },
  slope: {
    id: 'hrdem-wms-slope',
    layerId: 'hrdem-wms-slope-layer',
    visible: false,
    opacity: 0.8,
    style: 'slope_grey',
  },
  hillshade: {
    id: 'hrdem-wms-hillshade',
    layerId: 'hrdem-wms-hillshade-layer',
    visible: false,
    opacity: 0.8,
    style: 'hillshade',
  },
  quebecPublicLand: {
    id: 'quebec-public-land',
    layerId: 'quebec-public-land-layer',
    visible: true,
    opacity: 0.7,
  },
  relief: {
    id: 'hrdem-relief',
    layerId: 'hrdem-relief-layer',
    visible: false,
    opacity: 0.8,
    colormap: 'cividis',
    // Physical display range in metres — converted to DN when building the tile URL
    vminMetres: 0.0,
    vmaxMetres: 3.0,
  },
};
