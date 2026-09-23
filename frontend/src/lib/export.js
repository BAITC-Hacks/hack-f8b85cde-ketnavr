import { URGENCY } from './contract.js';

export const exportColumns = [
  ['sku', 'Артикул'], ['product_name', 'Наименование'], ['supplier', 'Поставщик'],
  ['category', 'Категория'], ['unit', 'Ед. изм.'], ['stock_qty', 'Остаток'],
  ['in_transit_qty', 'В пути'], ['recommended_order_qty', 'К заказу'],
  ['coverage_days', 'Запас, дней'], ['avg_daily_demand', 'Средний спрос в день'],
  ['lead_time_days', 'Срок поставки, дней'], ['moq', 'MOQ'],
  ['unit_price_kzt', 'Цена за единицу, ₸'], ['urgency', 'Срочность'], ['reason', 'Обоснование'],
];

export function exportValues(row, { mode, asOf }) {
  return [
    ...exportColumns.map(([key]) => key === 'urgency' ? URGENCY[row.urgency].label : row[key]),
    asOf,
    mode === 'demo' || row.synthetic ? 'ДЕМО / синтетические данные' : 'Backend',
  ];
}

const headers = [...exportColumns.map(([, label]) => label), 'Дата среза', 'Источник'];

function csvCell(value) {
  let text = value === null || value === undefined ? '' : String(value);
  // Prevent formula execution when opening arbitrary API text in a spreadsheet.
  if (typeof value === 'string' && /^[\s\uFEFF]*[=+@-]/u.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function buildCsv(rows, context) {
  return '\uFEFF' + [headers, ...rows.map((row) => exportValues(row, context))]
    .map((row) => row.map(csvCell).join(';')).join('\r\n');
}

export async function buildWorkbook(rows, context) {
  const module = await import('exceljs');
  const ExcelJS = module.default || module;
  const workbook = new ExcelJS.Workbook();
  workbook.creator = 'Запас';
  const sheet = workbook.addWorksheet('Рекомендации', { views: [{ state: 'frozen', ySplit: 1 }] });
  sheet.addRow(headers);
  rows.forEach((row) => sheet.addRow(exportValues(row, context)));
  sheet.autoFilter = { from: { row: 1, column: 1 }, to: { row: 1, column: headers.length } };
  sheet.getRow(1).height = 30;
  sheet.getRow(1).eachCell((cell) => {
    cell.font = { bold: true, color: { argb: 'FFFFFFFF' } };
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF172C31' } };
    cell.alignment = { vertical: 'middle', wrapText: true };
  });
  sheet.columns.forEach((column, i) => {
    column.width = i === 14 ? 75 : i === 1 ? 42 : i === 16 ? 34 : 20;
    if (i >= 5 && i <= 12) column.numFmt = '#,##0.##';
  });
  sheet.eachRow((row, index) => {
    if (index === 1) return;
    row.height = 48;
    row.eachCell((cell) => {
      cell.alignment = { vertical: 'middle', wrapText: true };
      if (index % 2 === 0) cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFF2F6F5' } };
    });
  });
  return workbook;
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadRows(rows, format, context) {
  if (!rows.length) throw new Error('Нет строк для выгрузки.');
  const basename = `${context.mode === 'demo' ? 'DEMO-' : ''}recommendations-${context.asOf}`;
  if (format === 'csv') {
    saveBlob(new Blob([buildCsv(rows, context)], { type: 'text/csv;charset=utf-8' }), `${basename}.csv`);
  } else {
    const workbook = await buildWorkbook(rows, context);
    saveBlob(new Blob([await workbook.xlsx.writeBuffer()], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), `${basename}.xlsx`);
  }
}

