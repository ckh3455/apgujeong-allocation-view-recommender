const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const VIEW_DIR = path.join(ROOT, 'current-view');
const SOURCE = path.join(VIEW_DIR, 'calc_view_angle_distribution.js');
const TEMP = path.join(ROOT, 'data', '_simultaneous_conservative_calc.js');
const OUT_JSON = path.join(ROOT, 'data', 'simultaneous_conservative_view_by_pyeong.json');
const OUT_CSV = path.join(ROOT, 'data', 'simultaneous_conservative_view_by_pyeong.csv');
const OUT_MD = path.join(ROOT, 'data', 'simultaneous_conservative_view_by_pyeong.md');
const STEP_M = Number(process.env.FACADE_SAMPLE_STEP_M || 8);

let source = fs.readFileSync(SOURCE, 'utf8');
source = source.replace(/const BASE = [^;]+;/, `const BASE = ${JSON.stringify(VIEW_DIR)};`);
source = source.replace(/const FACADE_SAMPLE_STEP_M = [^;]+;/, `const FACADE_SAMPLE_STEP_M = ${STEP_M};`);
source = source.replace(
  /function normalizedFloorCount\(props\) \{[\s\S]*?\n\}/,
  `function normalizedFloorCount(props) {\n  return Number(props.floors || 0);\n}`
);

const marker = 'const summary = {};';
const idx = source.indexOf(marker);
if (idx < 0) throw new Error('Calculation tail marker not found');

const tail = String.raw`
const ZONE4_TYPE_PYEONG_LABEL = {
  '59': '25', '84': '34', '96': '40', '105': '43', '47': '47',
  '114': '47', '115': '47', '120': '49', '126': '52', '147': '60',
  '154': '63', '164': '67', '166': '68', '170': '70', '177': '72',
  '178': '72', '183': '74', '188': '77', 'D183': '74'
};

function zone4TypeKey(value) {
  const t = String(value || '').trim().toUpperCase().replace(/\s+/g, '');
  const m = t.match(/^(P\d+|D?\d+)/);
  return m ? m[1] : t;
}

function displayPyeong(zoneId, unitType) {
  const raw = String(unitType || '').trim();
  if (String(zoneId) === '4') {
    const key = zone4TypeKey(raw);
    if (ZONE4_TYPE_PYEONG_LABEL[key]) return ZONE4_TYPE_PYEONG_LABEL[key];
    const m = raw.match(/\d+/);
    return m ? String(Number(m[0])) : raw;
  }
  return raw;
}

function unitMultiplicity(unitType) {
  const parts = String(unitType || '').split(',').map(v => v.trim()).filter(Boolean);
  return Math.max(1, parts.length);
}

function groupKey(zoneId, pyeong) { return String(zoneId) + '|' + String(pyeong); }
function pct(n, d) { return d ? +(n / d * 100).toFixed(2) : 0; }
function n2(v) { return +Number(v || 0).toFixed(2); }

const groups = new Map();
const perFloor = [];
const sorted = footprints.slice().sort((a, b) =>
  String(a.zoneId).localeCompare(String(b.zoneId)) ||
  String(a.dong).localeCompare(String(b.dong)) ||
  String(a.unitType).localeCompare(String(b.unitType))
);

let done = 0;
for (const footprint of sorted) {
  const candidateData = collectFacadeCandidates(footprint, footprints, riverContext);
  const floors = Math.max(1, Math.round(Number(footprint.props?.floors || footprint.floors || 1)));
  const pyeong = displayPyeong(footprint.zoneId, footprint.unitType);
  const weight = unitMultiplicity(footprint.unitType);
  const key = groupKey(footprint.zoneId, pyeong);
  if (!groups.has(key)) {
    groups.set(key, {
      zoneId: String(footprint.zoneId), pyeong, rawTypes: new Set(),
      footprintCount: 0, weightedCount: 0, angleSum: 0,
      minAngle: Infinity, maxAngle: -Infinity,
      ge100: 0, b90_100: 0, ge90: 0, b80_90: 0, ge80: 0,
      b70_80: 0, b60_70: 0, lt60: 0, lt80: 0
    });
  }
  const g = groups.get(key);
  g.rawTypes.add(String(footprint.unitType || ''));
  g.footprintCount += 1;

  for (let floor = 1; floor <= floors; floor += 1) {
    const angle = summarizeFacadeCandidates(candidateData, floorEyeHeight(footprint, floor));
    g.weightedCount += weight;
    g.angleSum += angle * weight;
    g.minAngle = Math.min(g.minAngle, angle);
    g.maxAngle = Math.max(g.maxAngle, angle);
    if (angle >= 100) g.ge100 += weight;
    if (angle >= 90 && angle < 100) g.b90_100 += weight;
    if (angle >= 90) g.ge90 += weight;
    if (angle >= 80 && angle < 90) g.b80_90 += weight;
    if (angle >= 80) g.ge80 += weight;
    if (angle >= 70 && angle < 80) g.b70_80 += weight;
    if (angle >= 60 && angle < 70) g.b60_70 += weight;
    if (angle < 60) g.lt60 += weight;
    if (angle < 80) g.lt80 += weight;
    perFloor.push({
      zone: String(footprint.zoneId) + '구역', dong: String(footprint.dong || ''),
      pyeong, rawType: String(footprint.unitType || ''), fid: String(footprint.fid || ''),
      floor, angle, weight
    });
  }
  done += 1;
  if (done % 10 === 0) console.error('processed ' + done + '/' + sorted.length);
}

const rows = [...groups.values()].map(g => ({
  구역: g.zoneId + '구역',
  평형: g.pyeong,
  계산단위: g.weightedCount,
  유닛폴리곤수: g.footprintCount,
  원본유닛타입: [...g.rawTypes].sort().join(' / '),
  평균조망각: n2(g.angleSum / g.weightedCount),
  최소조망각: Number.isFinite(g.minAngle) ? g.minAngle : 0,
  최대조망각: Number.isFinite(g.maxAngle) ? g.maxAngle : 0,
  '100도이상_pct': pct(g.ge100, g.weightedCount),
  '90_100도_pct': pct(g.b90_100, g.weightedCount),
  '90도이상_pct': pct(g.ge90, g.weightedCount),
  '80_90도_pct': pct(g.b80_90, g.weightedCount),
  '80도이상_pct': pct(g.ge80, g.weightedCount),
  '70_80도_pct': pct(g.b70_80, g.weightedCount),
  '60_70도_pct': pct(g.b60_70, g.weightedCount),
  '60도미만_pct': pct(g.lt60, g.weightedCount),
  '80도미만_pct': pct(g.lt80, g.weightedCount)
})).sort((a, b) => {
  const za = Number(String(a.구역).match(/\d+/)?.[0] || 99);
  const zb = Number(String(b.구역).match(/\d+/)?.[0] || 99);
  if (za !== zb) return za - zb;
  const pa = Number(String(a.평형).match(/\d+/)?.[0] || 9999);
  const pb = Number(String(b.평형).match(/\d+/)?.[0] || 9999);
  return pa - pb || String(a.평형).localeCompare(String(b.평형));
});

const zoneSummary = ['2','3','4','5'].map(zoneId => {
  const zr = rows.filter(r => r.구역 === zoneId + '구역');
  const count = zr.reduce((s, r) => s + r.계산단위, 0);
  const angleSum = zr.reduce((s, r) => s + r.평균조망각 * r.계산단위, 0);
  return {
    구역: zoneId + '구역', 평형수: zr.length, 계산단위: count,
    평균조망각: count ? n2(angleSum / count) : 0,
    최소조망각: zr.length ? Math.min(...zr.map(r => r.최소조망각)) : 0,
    최대조망각: zr.length ? Math.max(...zr.map(r => r.최대조망각)) : 0
  };
});

const expectedZone2 = {
  '25': [328,13.47], '32': [256,12.38], '37': [64,0], '41': [440,70.14],
  '45,46': [816,79.29], '51,52': [706,72.48], '55,56': [338,103.96],
  '60': [253,68.65], '65': [112,73.22], '70': [44,114.68],
  '79': [129,87.35], '87': [129,85.81]
};
const validation = rows.filter(r => r.구역 === '2구역').map(r => {
  const exp = expectedZone2[String(r.평형)];
  return {
    평형: r.평형, 계산단위: r.계산단위, 평균조망각: r.평균조망각,
    기대계산단위: exp?.[0] ?? null, 기대평균각: exp?.[1] ?? null,
    계산단위차이: exp ? r.계산단위 - exp[0] : null,
    평균각차이: exp ? n2(r.평균조망각 - exp[1]) : null
  };
});

const output = {
  generatedAt: new Date().toISOString(),
  method: {
    sourceIndexLogic: 'APGUJEONG-VIEW/calc_view_angle_distribution.js',
    zonesCalculatedTogether: ['2','3','4','5'],
    riverLine: 'hangang_line_all.geojson',
    facadeSampleStepM: FACADE_SAMPLE_STEP_M,
    angleRoundingDeg: 1,
    blockers: '2·3·4·5구역 전체 유닛 폴리곤 동시 차폐',
    floorCount: 'GeoJSON floors 원값',
    weight: 'unit_type 쉼표 분리 개수 × 층수'
  },
  river: { lineCount: riverContext.lineCount, lengthM: Math.round(riverContext.sourceLength), scanPoints: riverContext.points.length },
  zoneSummary, validationAgainstUserZone2: validation, rows
};

fs.writeFileSync(${JSON.stringify(OUT_JSON)}, JSON.stringify(output, null, 2) + '\n', 'utf8');
const headers = Object.keys(rows[0]);
const esc = v => {
  const s = String(v ?? '');
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
};
fs.writeFileSync(${JSON.stringify(OUT_CSV)}, '\uFEFF' + headers.join(',') + '\n' + rows.map(r => headers.map(h => esc(r[h])).join(',')).join('\n') + '\n', 'utf8');
const md = [
  '# 2·3·4·5구역 동시 계산 보수적 한강 조망각', '',
  '- 한강라인: `hangang_line_all.geojson`',
  '- 외벽 표본 간격: `' + FACADE_SAMPLE_STEP_M + 'm`',
  '- 방위각: `1° 단위`',
  '- 차폐: `2·3·4·5구역 전체 건물 동시 반영`',
  '- 계산단위: `unit_type 쉼표 분리 개수 × 층수`', '',
  '| 구역 | 평형 | 계산단위 | 평균각 | 최소~최대 | 100°+ | 90~100° | 90°+ | 80~90° | 80°+ | 70~80° | 60~70° | 60° 미만 | 80° 미만 |',
  '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|'
];
for (const r of rows) md.push('| ' + [r.구역,r.평형,r.계산단위,r.평균조망각 + '°',r.최소조망각 + '~' + r.최대조망각 + '°',r['100도이상_pct']+'%',r['90_100도_pct']+'%',r['90도이상_pct']+'%',r['80_90도_pct']+'%',r['80도이상_pct']+'%',r['70_80도_pct']+'%',r['60_70도_pct']+'%',r['60도미만_pct']+'%',r['80도미만_pct']+'%'].join(' | ') + ' |');
md.push('', '## 2구역 어제 표 대조', '', '| 평형 | 계산단위 차이 | 평균각 차이 |', '|---|---:|---:|');
for (const v of validation) md.push('| ' + v.평형 + ' | ' + v.계산단위차이 + ' | ' + v.평균각차이 + '° |');
fs.writeFileSync(${JSON.stringify(OUT_MD)}, md.join('\n') + '\n', 'utf8');
console.log(JSON.stringify({stepM:FACADE_SAMPLE_STEP_M, footprintCount:footprints.length, rowCount:rows.length, zoneSummary, validation}, null, 2));
`;

source = source.slice(0, idx) + tail;
fs.mkdirSync(path.dirname(TEMP), { recursive: true });
fs.writeFileSync(TEMP, source, 'utf8');
const result = spawnSync(process.execPath, [TEMP], { cwd: ROOT, encoding: 'utf8', maxBuffer: 1024 * 1024 * 20 });
process.stdout.write(result.stdout || '');
process.stderr.write(result.stderr || '');
if (result.status !== 0) process.exit(result.status || 1);
