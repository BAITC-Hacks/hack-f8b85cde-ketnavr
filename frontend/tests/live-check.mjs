// Read-only integration audit of the running local frontend proxy.
// Run explicitly: node tests/live-check.mjs
import assert from 'node:assert/strict';
import { getRecommendations } from '../src/lib/api.js';
import { filterRows, sortRows, summarize } from '../src/lib/data.js';
import { buildCsv, buildWorkbook, exportValues } from '../src/lib/export.js';
import ExcelJS from 'exceljs';

const origin = 'http://127.0.0.1:5173';
const times = [];
const read = async () => {
  const start = performance.now();
  const data = await getRecommendations({ fetchImpl: (path, options) => fetch(`${origin}${path}?ai=true`, options) });
  times.push(Math.round(performance.now() - start));
  return data;
};
const first = await read();
const second = await read();
assert.deepEqual(first, second, 'The saved snapshot changed between reads');
const rows = first.recommendations;
assert.equal(rows.length, 221, 'Expected the agreed complete snapshot');
assert.equal(rows.filter(row => row.urgency === 'critical').length, 177);
assert.equal(rows.filter(row => row.urgency === 'soon').length, 44);
assert.ok(rows.every(row => !row.synthetic));
assert.ok(rows.every(row => row.recommended_order_qty > 0));
assert.ok(rows.every(row => row.moq && Math.abs(row.recommended_order_qty / row.moq - Math.round(row.recommended_order_qty / row.moq)) < 0.000001));
assert.ok(rows.filter(row => row.urgency === 'critical').every(row => row.coverage_days <= row.lead_time_days));
assert.ok(rows.filter(row => row.urgency === 'soon').every(row => row.coverage_days >= row.lead_time_days));

const filters = { search: '', supplier: 'SystemElectric', category: '', urgency: 'soon' };
const selected = filterRows(rows, filters);
assert.equal(selected.length, 8);
assert.equal(filterRows(rows, { ...filters, search: 'NOT-A-REAL-SKU' }).length, 0);
assert.deepEqual(sortRows(rows, 'original'), rows);
assert.deepEqual(sortRows(rows), sortRows([...rows].reverse()));

for (const scope of [rows, selected]) {
  const sorted = sortRows(scope, 'original');
  const context = { mode: 'api', asOf: first.as_of };
  const csv = buildCsv(sorted, context);
  assert.equal(csv.charCodeAt(0), 0xFEFF);
  assert.ok(!csv.includes('ДЕМО / синтетические данные'));
  for (const row of sorted) assert.ok(csv.includes(row.sku.replaceAll('"', '""')));
  const built = await buildWorkbook(sorted, context);
  const reloaded = new ExcelJS.Workbook();
  await reloaded.xlsx.load(await built.xlsx.writeBuffer());
  const sheet = reloaded.getWorksheet('Рекомендации');
  assert.equal(sheet.rowCount, sorted.length + 1);
  assert.equal(sheet.getCell('I1').value, 'Покрытие с учётом пути, дней');
  for (let index = 0; index < sorted.length; index++) {
    const expected = exportValues(sorted[index], context);
    for (let column = 0; column < expected.length; column++) {
      assert.equal(sheet.getCell(index + 2, column + 1).value, expected[column]);
    }
  }
}
const counts = key => Object.fromEntries([...new Set(rows.map(row => row[key]))].map(value => [value, rows.filter(row => row[key] === value).length]));
console.log(JSON.stringify({ count: rows.length, asOf: first.as_of, responseMs: times, suppliers: counts('supplier'), urgency: counts('urgency'), summary: summarize(rows), exports: ['221 rows', '8 filtered rows'], assertions: 'passed', distinctReasons: new Set(rows.map(row => row.reason)).size }, null, 2));
