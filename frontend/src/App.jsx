import React, { useEffect, useState } from "react";
import { MapContainer, TileLayer, useMap, GeoJSON } from "react-leaflet";
import "leaflet/dist/leaflet.css"; // Import Leaflet's default styles
import * as L from "leaflet";
import "leaflet.vectorgrid";
import GeoRasterLayer from "georaster-layer-for-leaflet";
import parseGeoraster from "georaster"
import chroma from "chroma-js"

function ESRIVectorLayer() {
  const map = useMap();

  useEffect(() => {
    const vectorTileLayer = L.vectorGrid.protobuf(
      "https://basemaps.arcgis.com/arcgis/rest/services/World_Basemap_v2/VectorTileServer/tile/{z}/{y}/{x}.pbf",
      {
        vectorTileLayerStyles: {}, // Empty for now
        attribution: '&copy; <a href="https://www.esri.com/">ESRI</a>',
        interactive: true, // Enable interactivity for debugging
        getFeatureId: (feature) => feature.properties.id, // Log feature IDs
        onEachFeature: (feature, layer) => {
          console.log("Feature:", feature); // Log feature details
        },
      }
    );

    vectorTileLayer.addTo(map);
  }, [map]);

  return null;
}

function BoulderPinsLayer() {
  const [geojson, setGeojson] = useState(null);

  useEffect(() => {
    fetch("/data/all_boulders.geojson")
      .then(res => res.json())
      .then(data => setGeojson(data));
  }, []);

  // Function to bind popups
  function onEachFeature(feature, layer) {
    let popupContent = `<strong>${feature.properties.name}</strong>`;
    if (feature.properties.description && feature.properties.description.trim() !== "") {
      popupContent += `<br>${feature.properties.description}`;
    }
    layer.bindPopup(popupContent);
  }

  return geojson ? <GeoJSON data={geojson} onEachFeature={onEachFeature} /> : null;
}


function DTMGeoTIFFLayer() {
  const map = useMap();

  useEffect(() => {
    const tiffUrl = `/data/dtm/morin_heights_dtm_slope.tif`;
    
    fetch(tiffUrl)
      .then(response => response.arrayBuffer())
      .then(arrayBuffer => parseGeoraster(arrayBuffer))
      .then(georaster => {
        const tiffLayer = new GeoRasterLayer({
          georaster,
          opacity: 0.6,
          pixelValuesToColorFn: values => {
            const elevation = values[0];
            if (elevation === null) return null;
            // Example: Viridis colormap
            const scale = chroma.scale('viridis').domain([georaster.mins[0], georaster.maxs[0]]);
            return scale(elevation).hex();
          }
        });
        tiffLayer.addTo(map);
      });

    return () => {

    };
  }, [map]);
  return null;
}

function App() {
  return (
    <div style={{ height: "100vh", width: "100vw" }}>
      <MapContainer
        center={[46.027, -74.1915]} // Default center
        zoom={16}
        minZoom={3}      // Set your desired minimum zoom
        maxZoom={22}     // Set your desired maximum zoom
        style={{ height: "100%", width: "100%" }}
      >
        {/* Base WMTS Layer */}
        <TileLayer
          url="https://servicesmatriciels.mern.gouv.qc.ca/erdas-iws/ogc/wmts/Imagerie_Continue/Imagerie_GQ/default/GoogleMapsCompatibleExt2:epsg:3857/{z}/{y}/{x}.jpg"
          attribution='&copy; Gouvernement du Québec'
          maxNativeZoom={18} // or whatever the highest zoom level your tiles support
          maxZoom={22}       // allow users to zoom in further
        >
        </TileLayer>
        {/* ESRI Vector Tile Layer */}
        {/* <ESRIVectorLayer /> */}
        {/* DTM GeoTIFF Layer */}
        {/* <DTMGeoTIFFLayer />*/}
        <TileLayer
          url="http://localhost:8000/cog/tiles/WebMercatorQuad/{z}/{x}/{y}?url=/home/sjjohnst/climbing-detection/data/dtm/laurentides_dtm_cog.tif&algorithm=slope&colormap_name=viridis&rescale=0,100"
          attribution="Laurentides DTM Slope via Titiler"
          maxZoom={22}
          maxNativeZoom={14}
          opacity={0.9}
        />
        <BoulderPinsLayer />
      </MapContainer>
    </div>
  )
}

export default App;