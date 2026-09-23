import { URGENCY } from './contract.js';

export const number = (value) => value === null || value === undefined ? '—' : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value);
export const money = (value) => value === null || value === undefined ? '—' : `${number(value)} ₸`;
export const dateLabel = (value) => new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(`${value}T12:00:00`));

export function filterRows(rows, filters, scope = 'all') {
  const search = filters.search.trim().toLocaleLowerCase('ru-RU');
  return rows.filter((row) => (
    (scope !== 'orders' || row.recommended_order_qty > 0)
    && (!filters.supplier || row.supplier === filters.supplier)
    && (!filters.category || row.category === filters.category)
    && (!filters.urgency || row.urgency === filters.urgency)
    && (!search || `${row.sku} ${row.product_name}`.toLocaleLowerCase('ru-RU').includes(search))
  ));
}

export function paginateRows(rows, page, pageSize = 50) {
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const currentPage = Math.max(1, Math.min(page, totalPages));
  const offset = (currentPage - 1) * pageSize;
  return {
    rows: rows.slice(offset, offset + pageSize),
    currentPage,
    totalPages,
    start: rows.length ? offset + 1 : 0,
    end: Math.min(offset + pageSize, rows.length),
  };
}

export function sortRows(rows, sort = 'priority') {
  // View sorting only. Never changes the recommended quantities or the explanations.
  return [...rows].sort((a, b) => {
    if (sort === 'original') return 0;
    const difference = sort === 'quantity'
      ? b.recommended_order_qty - a.recommended_order_qty
      : URGENCY[a.urgency].order - URGENCY[b.urgency].order;
    return difference || a.id.localeCompare(b.id, 'en');
  });
}

export function summarize(rows) {
  const toOrder = rows.filter((row) => row.recommended_order_qty > 0);
  const priced = toOrder.filter((row) => row.unit_price_kzt !== null);
  return {
    positions: rows.length,
    critical: rows.filter((row) => row.urgency === 'critical').length,
    toOrder: toOrder.length,
    amount: priced.length ? priced.reduce((sum, row) => sum + row.recommended_order_qty * row.unit_price_kzt, 0) : (toOrder.length ? null : 0),
    missingPrices: toOrder.length - priced.length,
  };
}

