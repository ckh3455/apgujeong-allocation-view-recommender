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
function displayPyeong(_zoneId, unitType) {
  // 어제 확정한 표와 동일하게 GeoJSON의 unit_type 표시값을 그대로 사용합니다.
  // 특히 4구역 47A와 47B를 합치지 않습니다.
  return String(unitType || '').trim();
}

function unitMultiplicity(unitType) {
  const parts = String(unitType || '').split(',').map(v => v.trim()).filter(Boolean);
  return Math.max(1, parts.length);
}

function gradeOf(angle) {
  if (angle >= 100) return '특A급';
  if (angle >= 81) return 'A급';
  if (angle >= 61) return 'B급';
  if (angle >= 41) return 'C급';
  if (angle >= 21) return 'D급';
  return 'E급';
}

function groupKey(zoneId, pyeong) { return String(zoneId) + '|' + String(pyeong); }
function pct(n, d) { return d ? +(n / d * 100).toFixed(2) : 0; }
function n2(v) { return +Number(v || 0).toFixed(2); }

const groups = new Map();
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
      grades: { '특A급': 0, 'A급': 0, 'B급': 0, 'C급': 0, 'D급': 0, 'E급': 0 }
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
    g.grades[gradeOf(angle)] += weight;
  }
  done += 1;
  if (done % 10 === 0) console.error('processed ' + done + '/' + sorted.length);
}

const rows = [...groups.values()].map(g => {
  const specialA = g.grades['특A급'];
  const a = g.grades['A급'];
  const b = g.grades['B급'];
  const c = g.grades['C급'];
  const d = g.grades['D급'];
  const e = g.grades['E급'];
  return {
    구역: g.zoneId + '구역',
    평형: g.pyeong,
    계산단위: g.weightedCount,
    유닛폴리곤수: g.footprintCount,
    원본유닛타입: [...g.rawTypes].sort().join(' / '),
    평균조망각: n2(g.angleSum / g.weightedCount),
    최소조망각: Number.isFinite(g.minAngle) ? g.minAngle : 0,
    최대조망각: Number.isFinite(g.maxAngle) ? g.maxAngle : 0,
    '특A급_100도이상_pct': pct(specialA, g.weightedCount),
    'A급_81_99도_pct': pct(a, g.weightedCount),
    'A급이상소계_pct': pct(specialA + a, g.weightedCount),
    'B급_61_80도_pct': pct(b, g.weightedCount),
    'B급이상소계_pct': pct(specialA + a + b, g.weightedCount),
    'C급_41_60도_pct': pct(c, g.weightedCount),
    'D급_21_40도_pct': pct(d, g.weightedCount),
    'E급_20도이하_pct': pct(e, g.weightedCount),
    'B급미만_pct': pct(c + d + e, g.weightedCount),
    등급별건수: { '특A급': specialA, 'A급': a, 'B급': b, 'C급': c, 'D급': d, 'E급': e }
  };
}).sort((a, b) => {
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
  const counts = { '특A급': 0, 'A급': 0, 'B급': 0, 'C급': 0, 'D급': 0, 'E급': 0 };
  for (const r of zr) for (const k of Object.keys(counts)) counts[k] += Number(r.등급별건수[k] || 0);
  return {
    구역: zoneId + '구역', 평형수: zr.length, 계산단위: count,
    평균조망각: count ? n2(angleSum / count) : 0,
    최소조망각: zr.length ? Math.min(...zr.map(r => r.최소조망각)) : 0,
    최대조망각: zr.length ? Math.max(...zr.map(r => r.최대조망각)) : 0,
    등급별건수: counts,
    등급별비율: Object.fromEntries(Object.entries(counts).map(([k,v]) => [k,pct(v,count)]))
  };
});

const expectedZone2 = {
  '25': { count:328, avg:13.47, pct:[0,0,0,5.79,15.85,78.35] },
  '32': { count:256, avg:12.38, pct:[0,0,0,11.72,3.91,84.38] },
  '37': { count:64, avg:0, pct:[0,0,0,0,0,100] },
  '41': { count:440, avg:70.14, pct:[24.09,7.5,18.18,22.5,22.27,5.45] },
  '45,46': { count:816, avg:79.29, pct:[33.82,15.69,10.54,27.21,6.86,5.88] },
  '51,52': { count:706, avg:72.48, pct:[26.35,5.67,13.6,35.41,6.52,12.46] },
  '55,56': { count:338, avg:103.96, pct:[54.44,11.24,22.49,11.83,0,0] },
  '60': { count:253, avg:68.65, pct:[22.92,7.51,36.36,7.51,6.72,18.97] },
  '65': { count:112, avg:73.22, pct:[14.29,3.57,64.29,0.89,16.96,0] },
  '70': { count:44, avg:114.68, pct:[56.82,43.18,0,0,0,0] },
  '79': { count:129, avg:87.35, pct:[25.58,3.1,56.59,14.73,0,0] },
  '87': { count:129, avg:85.81, pct:[25.58,3.1,56.59,14.73,0,0] }
};
const gradeCols = ['특A급_100도이상_pct','A급_81_99도_pct','B급_61_80도_pct','C급_41_60도_pct','D급_21_40도_pct','E급_20도이하_pct'];
const validation = rows.filter(r => r.구역 === '2구역').map(r => {
  const exp = expectedZone2[String(r.평형)];
  const actualPct = gradeCols.map(c => Number(r[c] || 0));
  return {
    평형: r.평형,
    계산단위차이: exp ? r.계산단위 - exp.count : null,
    평균각차이: exp ? n2(r.평균조망각 - exp.avg) : null,
    최대등급비율차이: exp ? n2(Math.max(...actualPct.map((v,i) => Math.abs(v - exp.pct[i])))) : null
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
    weight: 'unit_type 쉼표 분리 개수 × 층수',
    grades: { '특A급':'100도 이상','A급':'81~99도','B급':'61~80도','C급':'41~60도','D급':'21~40도','E급':'20도 이하' }
  },
  river: { lineCount: riverContext.lineCount, lengthM: Math.round(riverContext.sourceLength), scanPoints: riverContext.points.length },
  zoneSummary, validationAgainstUserZone2: validation, rows
};

fs.writeFileSync(${JSON.stringify(OUT_JSON)}, JSON.stringify(output, null, 2) + '\n', 'utf8');
const csvRows = rows.map(({등급별건수, ...r}) => r);
const headers = Object.keys(csvRows[0]);
const esc = v => {
  const s = String(v ?? '');
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
};
fs.writeFileSync(${JSON.stringify(OUT_CSV)}, '\uFEFF' + headers.join(',') + '\n' + csvRows.map(r => headers.map(h => esc(r[h])).join(',')).join('\n') + '\n', 'utf8');
const md = [
  '# 2·3·4·5구역 동시 계산 보수적 한강 조망각', '',
  '- 한강라인: `hangang_line_all.geojson`',
  '- 외벽 표본 간격: `' + FACADE_SAMPLE_STEP_M + 'm`',
  '- 방위각: `1° 단위`',
  '- 차폐: `2·3·4·5구역 전체 건물 동시 반영`',
  '- 계산단위: `unit_type 쉼표 분리 개수 × 층수`', '',
  '| 구역 | 평형 | 계산단위 | 평균각 | 최소~최대 | 특A | A | A이상 | B | B이상 | C | D | E | B미만 |',
  '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|'
];
for (const r of rows) md.push('| ' + [r.구역,r.평형,r.계산단위,r.평균조망각 + '°',r.최소조망각 + '~' + r.최대조망각 + '°',r['특A급_100도이상_pct']+'%',r['A급_81_99도_pct']+'%',r['A급이상소계_pct']+'%',r['B급_61_80도_pct']+'%',r['B급이상소계_pct']+'%',r['C급_41_60도_pct']+'%',r['D급_21_40도_pct']+'%',r['E급_20도이하_pct']+'%',r['B급미만_pct']+'%'].join(' | ') + ' |');
md.push('', '## 2구역 어제 표 대조', '', '| 평형 | 계산단위 차이 | 평균각 차이 | 최대 등급비율 차이 |', '|---|---:|---:|---:|');
for (const v of validation) md.push('| ' + v.평형 + ' | ' + v.계산단위차이 + ' | ' + v.평균각차이 + '° | ' + v.최대등급비율차이 + '%p |');
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
