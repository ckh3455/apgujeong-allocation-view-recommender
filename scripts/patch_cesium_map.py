from pathlib import Path

path = Path("index_view_candidates.html")
text = path.read_text(encoding="utf-8")

# Globe must remain visible.
text = text.replace("viewer.scene.globe.show = false;", "viewer.scene.globe.show = true;")

# Remove the candidate-entity zoom that can place the camera below the ellipsoid.
old_zoom = '''      await viewer.zoomTo(candidateEntities.length ? candidateEntities : source, new Cesium.HeadingPitchRange(
        Cesium.Math.toRadians(335),
        Cesium.Math.toRadians(-45),
        candidateEntities.length ? 650 : 900
      ));'''
new_zoom = '''      viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(127.03255, 37.52545, 920),
        orientation: {
          heading: Cesium.Math.toRadians(335),
          pitch: Cesium.Math.toRadians(-58),
          roll: 0
        }
      });
      viewer.scene.globe.show = true;
      viewer.scene.requestRender();'''
if old_zoom in text:
    text = text.replace(old_zoom, new_zoom, 1)

# After applying candidate presentation, make the actual extruded polygons visible and opaque.
old_candidate = '''        candidateEntities = applyCandidatePresentation();
      }'''
new_candidate = '''        candidateEntities = applyCandidatePresentation();
        for (const candidateEntity of candidateEntities) {
          candidateEntity.show = true;
          if (candidateEntity.polygon) {
            candidateEntity.polygon.show = true;
            candidateEntity.polygon.material = candidateEntity.baseColor || Cesium.Color.fromCssColorString("#ef4444");
            candidateEntity.polygon.outline = true;
            candidateEntity.polygon.outlineColor = Cesium.Color.BLACK;
          }
        }
      }'''
if old_candidate in text:
    text = text.replace(old_candidate, new_candidate, 1)

# Keep the globe and lighting stable after map changes.
map_anchor = '''      viewer.scene.globe.translucency.enabled = false;
      viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#d9e3ec");
      viewer.scene.requestRender();'''
map_replacement = '''      viewer.scene.globe.translucency.enabled = false;
      viewer.scene.globe.enableLighting = false;
      viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#d9e3ec");
      viewer.scene.requestRender();'''
if map_anchor in text:
    text = text.replace(map_anchor, map_replacement, 1)

path.write_text(text, encoding="utf-8")
print("Patched camera and candidate polygon visibility")
