from pathlib import Path

path = Path('app.py')
text = path.read_text(encoding='utf-8')

if 'import base64\n' not in text:
    text = text.replace('import json\n', 'import base64\nimport json\n', 1)

start = text.find('def render_candidate_map(candidates: pd.DataFrame, zone_name: str) -> None:')
end = text.find('\n\ndef render_grouped_view_tables', start)
if start < 0 or end < 0:
    raise RuntimeError('render_candidate_map block not found')

replacement = '''def render_candidate_map(candidates: pd.DataFrame, zone_name: str) -> None:
    """GitHub Pages의 정상 Cesium 지도를 iframe으로 열고 후보 설정을 URL로 전달합니다."""
    config = build_candidate_map_config(candidates, zone_name)
    if not config:
        st.info("지도에 표시할 조망후보 유닛이 없습니다.")
        return

    config_json = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(config_json.encode("utf-8")).decode("ascii").rstrip("=")
    map_url = f"https://ckh3455.github.io/APGUJEONG-VIEW/candidate.html?cfg={encoded}"

    unit_count = len(config["entries"])
    st.markdown(
        f"""
        <div style="margin:18px 0 8px;padding:11px 13px;border-left:5px solid #0b63d1;
                    background:rgba(11,99,209,.055);border-radius:8px;line-height:1.55;">
          <b>{config['title']}</b><br>
          <span style="color:rgba(49,51,63,.78);font-weight:650;">
            후보 유닛 {unit_count}개 · 각 평형 안에서 고유 유닛 수를 기준으로 균등 배정확률 표시
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    components.iframe(map_url, height=860, scrolling=False)
    st.caption("지도 유닛을 클릭하면 기존 GitHub Pages 지도와 같은 조망각·층별 레이·눈높이 360도 회전 기능을 사용할 수 있습니다.")
'''

text = text[:start] + replacement + text[end:]
path.write_text(text, encoding='utf-8')
print('Patched app.py to use GitHub Pages candidate iframe')
