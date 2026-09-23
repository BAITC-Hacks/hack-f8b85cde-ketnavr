import test from 'node:test';
import assert from 'node:assert/strict';
import { demoResponse } from '../src/data/demo.js';
import { parseRecommendationsResponse, ContractError } from '../src/lib/contract.js';
import { getRecommendations } from '../src/lib/api.js';
import { filterRows, sortRows, summarize } from '../src/lib/data.js';
import { buildCsv, buildWorkbook } from '../src/lib/export.js';

const payload = () => structuredClone(demoResponse);

test('both demo and API return the same validated schema', async () => {
  const demo = await getRecommendations({ mode: 'demo' });
  let requestUrl;
  const api = await getRecommendations({ fetchImpl: async (url, options) => {
    requestUrl = url;
    assert.equal(options.headers.Accept, 'application/json');
    return Response.json(demoResponse);
  } });
  assert.equal(requestUrl, '/api/recommendations');
  assert.deepEqual(api, demo);
  assert.equal(api.recommendations.length, 10);
});

test('an empty backend response is valid, not a connection error', () => {
  const data = parseRecommendationsResponse({ schema_version: '1.0', as_of: '2026-09-22', recommendations: [] });
  assert.deepEqual(data.recommendations, []);
});

test('rejects missing fields, duplicate IDs, invalid dates, quantities and urgency', () => {
  const mutations = [
    (data) => { delete data.recommendations[0].reason; },
    (data) => { data.recommendations[1].id = data.recommendations[0].id; },
    (data) => { data.as_of = '2026-02-30'; },
    (data) => { data.recommendations[0].recommended_order_qty = '120'; },
    (data) => { data.recommendations[0].stock_qty = -1; },
    (data) => { data.recommendations[0].urgency = '__proto__'; },
    (data) => { data.recommendations[0].synthetic = 'false'; },
  ];
  for (const mutate of mutations) {
    const data = payload();
    mutate(data);
    assert.throws(() => parseRecommendationsResponse(data), ContractError);
  }
});

test('optional missing prices remain null; zero is a known price', () => {
  const data = payload();
  delete data.recommendations[0].unit_price_kzt;
  data.recommendations[1].unit_price_kzt = 0;
  const rows = parseRecommendationsResponse(data).recommendations;
  assert.equal(rows[0].unit_price_kzt, null);
  assert.equal(rows[1].unit_price_kzt, 0);
  const sum = summarize(rows.slice(0, 2));
  assert.equal(sum.amount, 0);
  assert.equal(sum.missingPrices, 1);
  assert.equal(summarize([rows[0]]).amount, null);
});

test('filters combine with AND, preserve quantities, and sorting is deterministic', () => {
  const original = parseRecommendationsResponse(demoResponse).recommendations;
  const before = structuredClone(original);
  const filters = { search: 'автоматический', supplier: 'SystemElectric', category: 'Автоматика', urgency: 'critical' };
  const selected = filterRows(original, filters);
  assert.equal(selected.length, 1);
  assert.equal(selected[0].recommended_order_qty, 120);
  assert.equal(filterRows(original, { ...filters, supplier: 'ИЭК' }).length, 0);
  assert.deepEqual(sortRows(original), sortRows([...original].reverse()));
  assert.deepEqual(original, before);
});

test('HTTP error, broken connection and HTML never silently return demo data', async () => {
  await assert.rejects(getRecommendations({ fetchImpl: async () => new Response('failure', { status: 500 }) }), /HTTP 500/);
  await assert.rejects(getRecommendations({ fetchImpl: async () => { throw new TypeError('Failed to fetch'); } }), /Нет соединения/);
  await assert.rejects(getRecommendations({ fetchImpl: async () => new Response('<html>app</html>', { headers: { 'content-type': 'text/html' } }) }), /не JSON/);
});

test('CSV preserves Cyrillic, quotes, multiline explanations and escapes spreadsheet formulas', () => {
  const row = parseRecommendationsResponse(demoResponse).recommendations[0];
  const csv = buildCsv([{ ...row, product_name: '=HYPERLINK("evil")', reason: 'Строка; "кавычки"\nПеренос' }], { mode: 'demo', asOf: '2026-09-22' });
  assert.equal(csv.charCodeAt(0), 0xFEFF);
  assert.ok(csv.includes('"\'=HYPERLINK(""evil"")"'));
  assert.ok(csv.includes('"Строка; ""кавычки""\nПеренос"'));
  assert.ok(csv.includes('ДЕМО / синтетические данные'));
  assert.ok(csv.includes('2026-09-22'));
});

test('XLSX round-trip retains numbers, explanation and demo provenance', async () => {
  const rows = parseRecommendationsResponse(demoResponse).recommendations.slice(0, 2);
  const workbook = await buildWorkbook(rows, { mode: 'demo', asOf: '2026-09-22' });
  const buffer = await workbook.xlsx.writeBuffer();
  const ExcelJS = (await import('exceljs')).default;
  const reloaded = new ExcelJS.Workbook();
  await reloaded.xlsx.load(buffer);
  const sheet = reloaded.getWorksheet('Рекомендации');
  assert.equal(sheet.rowCount, 3);
  assert.equal(sheet.getCell('H2').value, 120);
  assert.equal(sheet.getCell('O2').value, rows[0].reason);
  assert.equal(sheet.getCell('P2').value, '2026-09-22');
  assert.equal(sheet.getCell('Q2').value, 'ДЕМО / синтетические данные');
});

