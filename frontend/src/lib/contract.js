export const URGENCY = {
  critical: { label: 'Критично', short: 'Критично', order: 0 },
  soon: { label: 'Заказать скоро', short: 'Скоро', order: 1 },
  normal: { label: 'Планово', short: 'Планово', order: 2 },
};

export class ContractError extends Error {
  constructor(message) {
    super(`Ответ backend не соответствует контракту: ${message}`);
    this.name = 'ContractError';
  }
}

function requireText(value, path) {
  if (typeof value !== 'string' || !value.trim()) throw new ContractError(`${path} — непустая строка.`);
  return value;
}

function quantity(value, path, optional = false) {
  if (optional && (value === null || value === undefined)) return null;
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    throw new ContractError(`${path} — число не меньше нуля${optional ? ' или null' : ''}.`);
  }
  return value;
}

export function isDateOnly(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

// One strict boundary for both demo fixtures and actual backend responses.
// Adapt a different backend schema HERE, never inside individual components.
export function parseRecommendationsResponse(payload) {
  if (!payload || typeof payload !== 'object' || payload.schema_version !== '1.0') {
    throw new ContractError('ожидается schema_version: "1.0".');
  }
  if (!isDateOnly(payload.as_of)) throw new ContractError('as_of — дата YYYY-MM-DD.');
  if (!Array.isArray(payload.recommendations)) throw new ContractError('recommendations — массив.');
  const ids = new Set();
  const recommendations = payload.recommendations.map((row, index) => {
    const path = `recommendations[${index}]`;
    if (!row || typeof row !== 'object') throw new ContractError(`${path} — объект.`);
    const id = requireText(row.id, `${path}.id`);
    if (ids.has(id)) throw new ContractError(`id "${id}" повторяется.`);
    ids.add(id);
    if (!Object.hasOwn(URGENCY, row.urgency)) throw new ContractError(`${path}.urgency — critical, soon или normal.`);
    if (row.synthetic !== undefined && typeof row.synthetic !== 'boolean') throw new ContractError(`${path}.synthetic — boolean.`);
    return {
      id,
      sku: requireText(row.sku, `${path}.sku`),
      product_name: requireText(row.product_name, `${path}.product_name`),
      supplier: requireText(row.supplier, `${path}.supplier`),
      category: requireText(row.category, `${path}.category`),
      unit: row.unit === undefined ? 'шт.' : requireText(row.unit, `${path}.unit`),
      stock_qty: quantity(row.stock_qty, `${path}.stock_qty`),
      in_transit_qty: quantity(row.in_transit_qty, `${path}.in_transit_qty`),
      recommended_order_qty: quantity(row.recommended_order_qty, `${path}.recommended_order_qty`),
      avg_daily_demand: quantity(row.avg_daily_demand, `${path}.avg_daily_demand`, true),
      coverage_days: quantity(row.coverage_days, `${path}.coverage_days`, true),
      lead_time_days: quantity(row.lead_time_days, `${path}.lead_time_days`, true),
      moq: quantity(row.moq, `${path}.moq`, true),
      unit_price_kzt: quantity(row.unit_price_kzt, `${path}.unit_price_kzt`, true),
      urgency: row.urgency,
      reason: requireText(row.reason, `${path}.reason`),
      synthetic: row.synthetic === true,
    };
  });
  return { schema_version: '1.0', as_of: payload.as_of, recommendations };
}

