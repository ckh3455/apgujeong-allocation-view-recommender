from pathlib import Path

path = Path("index_view_candidates.html")
text = path.read_text(encoding="utf-8")

# Any later code that hides the globe makes only the starry skybox visible.
text = text.replace("viewer.scene.globe.show = false;", "viewer.scene.globe.show = true;")

old_viewer = '''    const viewer = new Cesium.Viewer("cesiumContainer", {
      animation: false,
      timeline: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: true,
      baseLayerPicker: false,
      navigationHelpButton: false,
      infoBox: false,
      selectionIndicator: true,
      sceneMode: Cesium.SceneMode.SCENE3D,
      baseLayer: false,
      terrainProvider: new Cesium.EllipsoidTerrainProvider()
    });

    viewer.scene.globe.depthTestAgainstTerrain = false;'''

new_viewer = '''    const initialBaseProvider = new Cesium.UrlTemplateImageryProvider({
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
      minimumLevel: 0,
      maximumLevel: 19,
      tilingScheme: new Cesium.WebMercatorTilingScheme(),
      credit: "Esri World Street Map"
    });

    const viewer = new Cesium.Viewer("cesiumContainer", {
      animation: false,
      timeline: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: true,
      baseLayerPicker: false,
      navigationHelpButton: false,
      infoBox: false,
      selectionIndicator: true,
      sceneMode: Cesium.SceneMode.SCENE3D,
      baseLayer: new Cesium.ImageryLayer(initialBaseProvider),
      terrainProvider: new Cesium.EllipsoidTerrainProvider()
    });

    viewer.scene.globe.show = true;
    viewer.scene.globe.enableLighting = false;
    viewer.scene.globe.translucency.enabled = false;
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#d9e3ec");
    viewer.scene.globe.depthTestAgainstTerrain = false;
    viewer.scene.preRender.addEventListener(() => {
      if (!viewer.scene.globe.show) viewer.scene.globe.show = true;
      if (viewer.scene.globe.translucency.enabled) viewer.scene.globe.translucency.enabled = false;
    });'''

if old_viewer in text:
    text = text.replace(old_viewer, new_viewer, 1)
elif "const initialBaseProvider = new Cesium.UrlTemplateImageryProvider" in text:
    marker = '    viewer.scene.globe.depthTestAgainstTerrain = false;'
    forced = '''    viewer.scene.globe.show = true;
    viewer.scene.globe.enableLighting = false;
    viewer.scene.globe.translucency.enabled = false;
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#d9e3ec");
    viewer.scene.globe.depthTestAgainstTerrain = false;
    viewer.scene.preRender.addEventListener(() => {
      if (!viewer.scene.globe.show) viewer.scene.globe.show = true;
      if (viewer.scene.globe.translucency.enabled) viewer.scene.globe.translucency.enabled = false;
    });'''
    if "viewer.scene.preRender.addEventListener(() =>" not in text:
        text = text.replace(marker, forced, 1)
else:
    raise RuntimeError("viewer initialization block not found")

start_markers = [
    '    async function applyPublicBaseMap(mapId = "street") {',
    '    function applyPublicBaseMap(mapId = "street") {',
]
start = next((text.find(marker) for marker in start_markers if text.find(marker) >= 0), -1)
if start < 0:
    raise RuntimeError("applyPublicBaseMap function not found")

end_marker = "\n    function readStoredVworldKey()"
end = text.find(end_marker, start)
if end < 0:
    raise RuntimeError("readStoredVworldKey marker not found")

replacement = '''    function applyPublicBaseMap(mapId = "street") {
      if (publicBaseLayer) {
        viewer.imageryLayers.remove(publicBaseLayer, true);
        publicBaseLayer = null;
      }

      if (vworldLayer) {
        viewer.imageryLayers.remove(vworldLayer, true);
        vworldLayer = null;
      }

      const config = MAP_CONFIGS[mapId] || MAP_CONFIGS.street;
      const url = mapId === "satellite"
        ? "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        : "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}";

      const provider = new Cesium.UrlTemplateImageryProvider({
        url,
        minimumLevel: 0,
        maximumLevel: 19,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        credit: mapId === "satellite" ? "Esri World Imagery" : "Esri World Street Map"
      });

      publicBaseLayer = viewer.imageryLayers.addImageryProvider(provider, 0);
      publicBaseLayer.alpha = mapId === "light" ? 0.72 : 1.0;
      viewer.scene.globe.show = true;
      viewer.scene.globe.enableLighting = false;
      viewer.scene.globe.translucency.enabled = false;
      viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#d9e3ec");
      viewer.scene.requestRender();
      setActiveMapButton(mapId);
      setStatus(`${config.label} 배경을 적용했습니다.`);
    }
'''

text = text[:start] + replacement + text[end:]
text = text.replace(
    'setTimeout(() => applyPublicBaseMap("street"), 300);',
    'setTimeout(() => { applyPublicBaseMap("street"); }, 300);',
)

path.write_text(text, encoding="utf-8")
print("Patched index_view_candidates.html")
