const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = process.cwd();
const DATA_DIR = path.join(ROOT, 'data');
const SOURCE_URL = process.env.SOURCE_URL || 'http://127.0.0.1:8000/index_v55_zone_cache_light.html?summaryBuild=1';
const TARGET_ZONES = (process.env.TARGET_ZONES || '3,4,5').split(',').map(v => v.trim()).filter(Boolean);
const VIEW_MODE = process.env.VIEW_MODE || 'conservative';
const SUMMARY_PATH = path.join(DATA_DIR, 'view_summary.json');
const UNIT_CSV_PATH = path.join(DATA_DIR, 'view_unit_rows.csv');
const FLOOR_CSV_PATH = path.join(DATA_DIR, 'view_floor_rows.csv');

function csvEscape(value) {
  if (value === null || value === undefined) return '';
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function writeCsv(filePath, headers, rows) {
  const lines = [headers.join(',')];
  for (const row of rows) lines.push(headers.map(h => csvEscape(row[h])).join(','));
  fs.writeFileSync(filePath, '\uFEFF' + lines.join('\n') + '\n', 'utf8');
}

function numericKey(value) {
  const match = String(value ?? '').match(/\d+/);
  return match ? Number(match[0]) : Number.MAX_SAFE_INTEGER;
}

function sortRows(rows) {
  return rows.slice().sort((a, b) => {
    const z = numericKey(a.zoneId) - numericKey(b.zoneId);
    if (z) return z;
    const d = numericKey(a.dong) - numericKey(b.dong);
    if (d) return d;
    const s = numericKey(a.sourceFid) - numericKey(b.sourceFid);
    if (s) return s;
    return String(a.fid).localeCompare(String(b.fid));
  });
}

function buildDerivedCsvRows(summaryRows) {
  const unitHeaders = [
    'fid', 'sourceFid', 'zone', 'zoneId', 'dong', 'unitType', 'floors', 'heightM',
    'riverDistanceM', 'riverBearing', 'riverBearingName', 'topFloorViewAngle',
    'topFloorRange', 'bestViewAngle', 'bestFloorRange', 'bestAngleRange'
  ];
  const floorHeaders = [
    'fid', 'zone', 'zoneId', 'dong', 'unitType', 'floor', 'floors', 'viewAngle',
    'maxGap', 'angleRange', 'distanceMin', 'distanceMax'
  ];

  const unitRows = summaryRows.map(row => Object.fromEntries(unitHeaders.map(h => [h, row[h] ?? ''])));
  const floorRows = [];
  for (const row of summaryRows) {
    for (const band of row.floorBands || []) {
      const start = Math.max(1, Number(band.start || 1));
      const end = Math.min(Number(row.floors || start), Number(band.end || start));
      for (let floor = start; floor <= end; floor += 1) {
        floorRows.push({
          fid: row.fid,
          zone: row.zone,
          zoneId: row.zoneId,
          dong: row.dong,
          unitType: row.unitType,
          floor,
          floors: row.floors,
          viewAngle: band.viewAngle ?? 0,
          maxGap: band.maxGap ?? 0,
          angleRange: band.mainRange ?? '',
          distanceMin: band.distanceMin ?? 0,
          distanceMax: band.distanceMax ?? 0
        });
      }
    }
  }
  return { unitHeaders, floorHeaders, unitRows, floorRows };
}

async function main() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const oldSummary = fs.existsSync(SUMMARY_PATH)
    ? JSON.parse(fs.readFileSync(SUMMARY_PATH, 'utf8').replace(/^\uFEFF/, ''))
    : { rows: [] };

  const browser = await chromium.launch({
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--use-gl=swiftshader',
      '--enable-webgl',
      '--ignore-gpu-blocklist',
      '--disable-background-timer-throttling',
      '--disable-renderer-backgrounding'
    ]
  });

  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(60 * 60 * 1000);
  page.on('console', msg => console.log(`[browser:${msg.type()}] ${msg.text()}`));
  page.on('pageerror', error => console.error(`[pageerror] ${error.stack || error.message}`));
  page.on('requestfailed', request => {
    const url = request.url();
    if (!/tile|vworld|openstreetmap|arcgis|cartocdn/i.test(url)) {
      console.error(`[requestfailed] ${request.failure()?.errorText || ''} ${url}`);
    }
  });

  await page.route('**/*', async route => {
    const request = route.request();
    const url = request.url();
    const type = request.resourceType();
    const local = /^http:\/\/127\.0\.0\.1:8000\//.test(url);
    const cesium = /cesium\.com\/downloads\/cesiumjs/i.test(url);
    if (local || cesium || url.startsWith('data:') || url.startsWith('blob:')) {
      return route.continue();
    }
    if (['image', 'media', 'font'].includes(type) || /tile|vworld|openstreetmap|arcgis|cartocdn|cesium\.com\/ion/i.test(url)) {
      return route.abort();
    }
    return route.continue();
  });

  console.log(`Loading ${SOURCE_URL}`);
  await page.goto(SOURCE_URL, { waitUntil: 'domcontentloaded', timeout: 5 * 60 * 1000 });
  await page.waitForFunction(() => {
    try {
      return typeof loadZone === 'function' &&
        typeof prepareBothRiverModeAnalyses === 'function' &&
        typeof footprints !== 'undefined' &&
        Array.isArray(footprints) && footprints.length > 0;
    } catch (_) {
      return false;
    }
  }, null, { timeout: 10 * 60 * 1000 });

  const initial = await page.evaluate(() => ({
    footprints: footprints.length,
    currentZoneId,
    modes: Object.keys(RIVER_MODE_CONFIGS || {})
  }));
  console.log('Index ready:', JSON.stringify(initial));

  const generatedRows = [];
  const diagnostics = {};

  for (const zoneId of TARGET_ZONES) {
    console.log(`=== ${zoneId}구역 계산 시작 ===`);
    await page.evaluate(async ({ zoneId, viewMode }) => {
      await loadZone(zoneId);
      currentZoneId = zoneId;
      setActiveZoneButton(zoneId);
      if (!(typeof restoreCompletedZone === 'function' && restoreCompletedZone(zoneId))) {
        preparedRiverStateByMode.clear();
        resetViewAnalysisCache();
        riverModesReady = false;
        await prepareBothRiverModeAnalyses(zoneId);
      }
      activatePreparedRiverMode(viewMode, { zoneIds: [zoneId], draw: false });
      if (!restoreAnalysisCacheForMode(viewMode)) {
        throw new Error(`${zoneId}구역 ${viewMode} 분석 캐시를 불러오지 못했습니다.`);
      }
    }, { zoneId, viewMode: VIEW_MODE });

    const extracted = await page.evaluate(({ zoneId, viewMode }) => {
      const round = (value, digits = 0) => {
        const number = Number(value);
        if (!Number.isFinite(number)) return null;
        const scale = 10 ** digits;
        return Math.round(number * scale) / scale;
      };
      const rangeOfGap = gap => gap
        ? `${Math.round(Number(gap.start?.angle ?? 0))}~${Math.round(Number(gap.end?.angle ?? 0))}`
        : '';
      const biggestGap = summary => {
        const gaps = summary?.gaps || [];
        if (!gaps.length) return null;
        return gaps.slice().sort((a, b) => Number(b.size || 0) - Number(a.size || 0))[0];
      };
      const blockerRow = blocker => ({
        zone: String(blocker?.zoneName || blocker?.zone || ''),
        dong: String(blocker?.dong || ''),
        unitType: String(blocker?.unitType || ''),
        floors: Math.round(Number(blocker?.floors || 0)),
        distance: Math.round(Number(blocker?.distance || 0))
      });
      const normalizeBand = band => {
        const summary = band?.summary || {};
        const gap = biggestGap(summary.allOpenSummary);
        return {
          start: Math.max(1, Math.round(Number(band?.start || 1))),
          end: Math.max(1, Math.round(Number(band?.end || band?.start || 1))),
          viewAngle: Math.round(Number(summary.totalOpen || 0)),
          maxGap: Math.round(Number(summary.allOpenSummary?.maxGap || gap?.size || 0)),
          mainRange: rangeOfGap(gap),
          distanceMin: Math.round(Number(gap?.distanceMin || 0)),
          distanceMax: Math.round(Number(gap?.distanceMax || 0)),
          blockingFloors: (summary.blockingFloors || []).map(v => Math.round(Number(v))).filter(Number.isFinite),
          blockingBlockers: (summary.blockingBlockers || []).slice(0, 3).map(blockerRow)
        };
      };

      const rows = [];
      let missing = 0;
      for (const footprint of footprints) {
        if (normalizeZoneId(footprint.zoneName || footprint.props?.source_zone || '') !== String(zoneId)) continue;
        const analysis = viewAnalysisByFid.get(String(footprint.fid));
        if (!analysis) {
          missing += 1;
          continue;
        }
        let bands = (analysis.floorBands || []).map(normalizeBand);
        const floors = Math.max(1, Math.round(Number(footprint.floors || 1)));
        if (!bands.length) {
          const gap = biggestGap(analysis.allOpenSummary);
          bands = [{
            start: 1,
            end: floors,
            viewAngle: Math.round(Number(analysis.totalOpen || 0)),
            maxGap: Math.round(Number(analysis.allOpenSummary?.maxGap || gap?.size || 0)),
            mainRange: rangeOfGap(gap),
            distanceMin: Math.round(Number(gap?.distanceMin || 0)),
            distanceMax: Math.round(Number(gap?.distanceMax || 0)),
            blockingFloors: [],
            blockingBlockers: []
          }];
        }
        bands.sort((a, b) => a.start - b.start);
        const topBand = bands.find(b => b.start <= floors && b.end >= floors) || bands[bands.length - 1];
        const bestBand = bands.slice().sort((a, b) =>
          (b.viewAngle - a.viewAngle) || (b.maxGap - a.maxGap) || (b.end - a.end)
        )[0];
        const props = footprint.props || {};
        const sourceFid = props.source_fid ?? props.fid ?? String(footprint.fid).split('-').slice(1).join('-');
        rows.push({
          fid: String(footprint.fid),
          sourceFid,
          zone: `${zoneId}구역`,
          zoneId: String(zoneId),
          dong: String(footprint.dong || ''),
          unitType: String(footprint.unitType || ''),
          floors,
          heightM: round(footprint.totalHeight || footprint.height || 0, 1),
          riverDistanceM: round(analysis.riverDistance, 0),
          riverBearing: round(analysis.riverBearing, 0),
          riverBearingName: String(analysis.riverBearingName || ''),
          topFloorViewAngle: Number(topBand?.viewAngle || 0),
          topFloorRange: String(topBand?.mainRange || ''),
          bestViewAngle: Number(bestBand?.viewAngle || 0),
          bestFloorRange: bestBand.start === bestBand.end ? String(bestBand.start) : `${bestBand.start}-${bestBand.end}`,
          bestAngleRange: String(bestBand?.mainRange || ''),
          floorBands: bands,
          calculationMode: viewMode
        });
      }
      return {
        rows,
        diagnostics: {
          zoneId: String(zoneId),
          footprintCount: footprints.filter(fp => normalizeZoneId(fp.zoneName || fp.props?.source_zone || '') === String(zoneId)).length,
          analysisCount: rows.length,
          missingAnalysisCount: missing,
          floorCount: rows.reduce((sum, row) => sum + Number(row.floors || 0), 0),
          typeCounts: rows.reduce((acc, row) => {
            acc[row.unitType] = (acc[row.unitType] || 0) + 1;
            return acc;
          }, {})
        }
      };
    }, { zoneId, viewMode: VIEW_MODE });

    diagnostics[zoneId] = extracted.diagnostics;
    generatedRows.push(...extracted.rows);
    console.log(`${zoneId}구역 결과:`, JSON.stringify(extracted.diagnostics));
    if (!extracted.rows.length || extracted.diagnostics.missingAnalysisCount > 0) {
      throw new Error(`${zoneId}구역 계산 결과 불완전: ${JSON.stringify(extracted.diagnostics)}`);
    }
  }

  await browser.close();

  const replaceSet = new Set(TARGET_ZONES.map(String));
  const preservedRows = (oldSummary.rows || []).filter(row => !replaceSet.has(String(row.zoneId || '').trim()));
  const allRows = sortRows([...preservedRows, ...generatedRows]);

  const zoneCounts = Object.fromEntries(
    ['2', '3', '4', '5'].map(zone => [zone, allRows.filter(row => String(row.zoneId) === zone).length])
  );
  for (const zone of TARGET_ZONES) {
    if (!zoneCounts[zone]) throw new Error(`${zone}구역 행이 최종 결과에 없습니다.`);
  }

  const output = {
    generatedAt: new Date().toISOString(),
    source: {
      index: 'APGUJEONG-VIEW/index_v55_zone_cache_light.html',
      calculationMode: VIEW_MODE,
      replacedZones: TARGET_ZONES,
      preservedZones: [...new Set(preservedRows.map(row => String(row.zoneId || '')))].filter(Boolean).sort()
    },
    assumptions: {
      floorViewUsesEyeHeight: 'piloti_m + (floor - 0.5) * floor_h',
      facadeSampleStepM: 2,
      sameDongRule: '현재 v55 인덱스의 동일동 보정 외피·내부 관통 차단 로직',
      riverLine: VIEW_MODE === 'conservative' ? 'hangang_line_all.geojson' : 'hangang_line_new.geojson',
      note: '현재 운영 인덱스에서 구역별 전체 유닛·전층을 직접 계산해 생성'
    },
    diagnostics,
    rows: allRows
  };

  fs.writeFileSync(SUMMARY_PATH, JSON.stringify(output, null, 2) + '\n', 'utf8');
  const csv = buildDerivedCsvRows(allRows);
  writeCsv(UNIT_CSV_PATH, csv.unitHeaders, csv.unitRows);
  writeCsv(FLOOR_CSV_PATH, csv.floorHeaders, csv.floorRows);

  console.log('Final zone row counts:', JSON.stringify(zoneCounts));
  console.log(`Wrote ${SUMMARY_PATH}`);
  console.log(`Wrote ${UNIT_CSV_PATH} (${csv.unitRows.length} rows)`);
  console.log(`Wrote ${FLOOR_CSV_PATH} (${csv.floorRows.length} rows)`);
}

main().catch(async error => {
  console.error(error && (error.stack || error.message) || error);
  process.exitCode = 1;
});
