import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDownToLine, ArrowUpRight, Boxes, Check, ChevronLeft, ChevronRight, CircleHelp,
  ClipboardList, FileSpreadsheet, FlaskConical, Layers3, LoaderCircle, Package,
  RefreshCw, Search, SlidersHorizontal, TriangleAlert, Truck, Wallet, X,
} from 'lucide-react';
import { DEFAULT_MODE, getRecommendations } from './lib/api.js';
import { saveBackFrontError } from './lib/back-front-errors.js';
import { URGENCY } from './lib/contract.js';
import { dateLabel, filterRows, money, number, paginateRows, sortRows, summarize } from './lib/data.js';
import { downloadRows } from './lib/export.js';

const INITIAL_FILTERS = { search: '', supplier: '', category: '', urgency: '' };

function TableHelp() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const dismissOutside = (event) => { if (!ref.current?.contains(event.target)) setOpen(false); };
    const dismissEscape = (event) => { if (event.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', dismissOutside);
    document.addEventListener('keydown', dismissEscape);
    return () => {
      document.removeEventListener('pointerdown', dismissOutside);
      document.removeEventListener('keydown', dismissEscape);
    };
  }, [open]);

  return <span className="table-help" ref={ref}
    onPointerEnter={(event) => { if (event.pointerType === 'mouse') setOpen(true); }}
    onPointerLeave={() => { if (!ref.current?.querySelector(':focus-visible')) setOpen(false); }}
    onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <button type="button" className="table-help-button" aria-label="Как посмотреть обоснование заказа"
      aria-expanded={open} aria-controls="table-help-content" aria-describedby={open ? 'table-help-content' : undefined}
      onFocus={(event) => { if (event.currentTarget.matches(':focus-visible')) setOpen(true); }}
      onClick={() => setOpen((previous) => !previous)}>
      <CircleHelp size={19} strokeWidth={1.6} aria-hidden="true" />
    </button>
    <span id="table-help-content" className="table-help-popover" role="tooltip" hidden={!open}>
      <span className="table-help-text">Нажмите на товар, чтобы увидеть обоснование и исходные показатели.</span>
    </span>
  </span>;
}

function UrgencyBadge({ value }) {
  return <span className={`urgency urgency-${value}`}><span aria-hidden="true" />{URGENCY[value].label}</span>;
}

function Supplier({ name }) {
  return <span className="supplier"><span className={`supplier-mark ${name === 'ИЭК' ? 'supplier-iek' : ''}`} aria-hidden="true">{name === 'ИЭК' ? 'И' : name.slice(0, 2).toUpperCase()}</span><span>{name}</span></span>;
}

function Metric({ icon: Icon, label, value, note, tone = '' }) {
  return <article className={`metric ${tone}`}>
    <div className="metric-label"><span>{label}</span><Icon size={19} strokeWidth={1.7} aria-hidden="true" /></div>
    <div className="metric-value">{value}</div>
    <div className="metric-note">{note}</div>
  </article>;
}

function DetailDialog({ row, onClose, mode }) {
  const ref = useRef(null);
  useEffect(() => { if (row && ref.current && !ref.current.open) ref.current.showModal(); }, [row]);
  if (!row) return null;
  const facts = [
    ['На складе', `${number(row.stock_qty)} ${row.unit}`],
    ['В пути', `${number(row.in_transit_qty)} ${row.unit}`],
    ['Средний спрос в день', row.avg_daily_demand === null ? 'Не передан' : `${number(row.avg_daily_demand)} ${row.unit}`],
    ['Покрытие с учётом пути', row.coverage_days === null ? 'Не передано' : `${number(row.coverage_days)} дн.`],
    ['Срок поставки', row.lead_time_days === null ? 'Не передан' : `${number(row.lead_time_days)} дн.`],
    ['Минимальная партия (MOQ)', row.moq === null ? 'Не передана' : `${number(row.moq)} ${row.unit}`],
  ];
  return <dialog className="detail-dialog" ref={ref} onClose={onClose} aria-labelledby="detail-title" onClick={(event) => { if (event.target === event.currentTarget) ref.current.close(); }}>
    <div className="dialog-heading"><span className="eyebrow">Обоснование заказа</span><button className="icon-button" aria-label="Закрыть детали" onClick={() => ref.current.close()}><X size={21} /></button></div>
    <div className="detail-product-icon"><Package size={30} strokeWidth={1.5} /></div>
    <p className="mono muted detail-sku">{row.sku}</p>
    <h2 id="detail-title">{row.product_name}</h2>
    <div className="detail-meta"><Supplier name={row.supplier} /><UrgencyBadge value={row.urgency} /></div>
    <section className="reason-panel"><div><CircleHelp size={18} /><h3>{row.recommended_order_qty > 0 ? 'Почему такой заказ' : 'Почему заказ не требуется'}</h3></div><p>{row.reason}</p></section>
    <dl className="detail-facts">{facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    <div className="detail-total"><div><span>{row.recommended_order_qty > 0 ? 'Рекомендовано к заказу' : 'Заказ не требуется'}</span><strong>{number(row.recommended_order_qty)} <small>{row.unit}</small></strong></div><div className="detail-price"><span>Сумма по переданной цене</span><strong>{row.recommended_order_qty === 0 ? money(0) : row.unit_price_kzt === null ? 'Цена не указана' : money(row.recommended_order_qty * row.unit_price_kzt)}</strong></div></div>
    {(mode === 'demo' || row.synthetic) && <p className="demo-note"><FlaskConical size={16} />Синтетический пример. Не расчёт по исходным Excel-файлам.</p>}
  </dialog>;
}

export default function App() {
  const [mode, setMode] = useState(DEFAULT_MODE);
  const [reload, setReload] = useState(0);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [scope, setScope] = useState('orders');
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState('priority');
  const [selected, setSelected] = useState(null);
  const [exporting, setExporting] = useState('');
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setData(null);
    setSelected(null);
    setNotice(null);
    getRecommendations({ mode, signal: controller.signal, includeNoOrder: true })
      .then((response) => { if (!controller.signal.aborted) setData(response); })
      .catch((failure) => { if (!controller.signal.aborted) { saveBackFrontError(failure, { mode, endpoint: '/recommendations' }); setError('Ошибка при загрузке данных'); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [mode, reload]);

  const rows = data?.recommendations ?? [];
  const suppliers = useMemo(() => [...new Set(rows.map((row) => row.supplier))].sort(), [data]);
  const categories = useMemo(() => [...new Set(rows.map((row) => row.category))].sort(), [data]);
  const visibleRows = useMemo(() => sortRows(filterRows(rows, filters, scope), sort), [data, filters, sort, scope]);
  const orderCount = useMemo(() => rows.filter((row) => row.recommended_order_qty > 0).length, [data]);
  const pageData = useMemo(() => paginateRows(visibleRows, page), [visibleRows, page]);
  const summary = useMemo(() => summarize(visibleRows), [visibleRows]);
  const hasFilters = Object.values(filters).some(Boolean);
  const available = data && !loading && !error;
  useEffect(() => { setPage(1); }, [data, filters, sort, scope]);
  const setFilter = (key, value) => {
    if (key === 'urgency' && value === 'normal') setScope('all');
    setFilters((previous) => ({ ...previous, [key]: value }));
  };

  function changeScope(nextScope) {
    setScope(nextScope);
    if (nextScope === 'orders' && filters.urgency === 'normal') {
      setFilters((previous) => ({ ...previous, urgency: '' }));
    }
  }

  function leaveDemo() {
    setFilters(INITIAL_FILTERS);
    setScope('orders');
    setSelected(null);
    setMode('api');
  }

  async function exportData(format) {
    setExporting(format);
    setNotice(null);
    try {
      await downloadRows(visibleRows, format, { mode, asOf: data.as_of });
      setNotice({ type: 'success', text: `${format.toUpperCase()} подготовлен: ${visibleRows.length} строк. Скачивание началось.` });
    } catch (failure) {
      setNotice({ type: 'error', text: `Не удалось подготовить файл: ${failure.message}` });
    } finally {
      setExporting('');
    }
  }

  return <div className="app-shell">
    <a className="skip-link" href="#recommendations">Перейти к рекомендациям</a>
    <aside className="sidebar" aria-label="Навигация">
      <a className="brand" href="#recommendations" aria-label="Ketnavr, рекомендации"><img className="brand-wordmark" src="/ketnavr-wordmark-transparent.png" alt="Ketnavr" /></a>
      <div className="sidebar-caption">УПРАВЛЕНИЕ ЗАКУПКАМИ</div>
      <a className="nav-item active" href="#recommendations" aria-current="page"><ClipboardList size={20} /><span>Рекомендации</span><ChevronRight size={16} /></a>
      <div className="sidebar-context"><span className="sidebar-section-label">РАБОЧЕЕ ПРОСТРАНСТВО</span><div className="workspace-icon"><Layers3 size={20} /></div><strong>Планирование поставок</strong><p>Остатки, потребность<br />и обоснованный заказ.</p></div>
      <div className="sidebar-bottom"><div className="sidebar-rule" /><span className="small-caps">HACKALEM · 2026</span><p>От данных — к решению.</p><div className="team-avatar">З</div><div><strong>Команда закупок</strong><span>Рабочая панель</span></div></div>
    </aside>

    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb">Закупки <ChevronRight size={14} /><span>Рекомендации</span></div><div className="topbar-right"><span className="profile-avatar" aria-label="Dias Serikov">DS</span></div></header>
      <main id="recommendations">
            <div className="page-heading"><div><div className="eyebrow heading-eyebrow">ПЛАНИРОВАНИЕ И РЕКОМЕНДАЦИИ</div><h1>Заказ с ясным основанием</h1><p>Потребность в закупке с учётом остатков, поставок в пути и срочности.</p></div><div className="heading-actions"><button className="button button-outline" onClick={() => setReload((count) => count + 1)} disabled={loading || Boolean(exporting)}><RefreshCw size={17} className={loading ? 'spin' : ''} />Обновить</button></div><div className="hero-orbit hero-orbit-one" aria-hidden="true" /><div className="hero-orbit hero-orbit-two" aria-hidden="true" /><div className="hero-spark hero-spark-one" aria-hidden="true" /><div className="hero-spark hero-spark-two" aria-hidden="true" /></div>

        {mode === 'demo' && <div className="demo-banner" role="status"><FlaskConical size={18} /><div><strong>Демонстрационные данные</strong><span>Все товары и расчёты ниже синтетические. Выгрузка тоже будет помечена «ДЕМО».</span></div><button className="button demo-exit" onClick={leaveDemo} disabled={Boolean(exporting)}>К рабочим данным</button></div>}
        {notice && <div className={`notice notice-${notice.type}`} role={notice.type === 'error' ? 'alert' : 'status'}>{notice.type === 'success' ? <Check size={18} /> : <TriangleAlert size={18} />}<span>{notice.text}</span><button className="icon-button" aria-label="Закрыть сообщение" onClick={() => setNotice(null)}><X size={17} /></button></div>}

        <div className="overview-heading"><span>Обзор {hasFilters ? 'текущей выборки' : 'рекомендаций'}</span><span>{data ? `Данные на ${dateLabel(data.as_of)}` : 'Ожидаем данные расчёта'}</span></div>
        <section className="metrics" aria-label="Сводка по текущей выборке">
          <Metric icon={Boxes} label="Товарных позиций" value={available ? number(summary.positions) : '—'} note={hasFilters ? 'С учётом выбранных фильтров' : scope === 'orders' ? 'В списке к закупке' : 'В полном расчёте'} />
          <Metric icon={TriangleAlert} label="Критичный запас" value={available ? number(summary.critical) : '—'} note="Приоритет указан в расчёте" tone="metric-critical" />
          <Metric icon={Truck} label="Позиций к заказу" value={available ? number(summary.toOrder) : '—'} note="С рекомендованным количеством > 0" />
          <Metric icon={Wallet} label={summary.missingPrices ? 'Сумма по известным ценам' : 'Сумма рекомендаций'} value={available ? money(summary.amount) : '—'} note={summary.missingPrices ? `Без цены: ${summary.missingPrices} поз. — сумма неполная` : 'Количество × закупочная цена'} tone="metric-amount" />
        </section>

        <section className="recommendation-panel" aria-labelledby="table-title">
          <div className="panel-heading"><div className="panel-title"><TableHelp /><h2 id="table-title">{scope === 'orders' ? 'Рекомендации к закупке' : 'Расчёт запасов'}</h2><span className="count-badge">{available ? visibleRows.length : '—'}</span></div><div className="export-actions"><button className="button button-quiet export-csv" onClick={() => exportData('csv')} disabled={!available || !visibleRows.length || Boolean(exporting)}>{exporting === 'csv' ? <LoaderCircle size={17} className="spin" /> : <ArrowDownToLine size={17} />}CSV</button><button className="button button-primary" onClick={() => exportData('xlsx')} disabled={!available || !visibleRows.length || Boolean(exporting)}>{exporting === 'xlsx' ? <LoaderCircle size={17} className="spin" /> : <FileSpreadsheet size={17} />}Скачать Excel</button></div></div>

          <div className="scope-toolbar"><div className="scope-switch" role="group" aria-label="Список товаров">
            <button type="button" aria-pressed={scope === 'orders'} onClick={() => changeScope('orders')} disabled={!available}>К закупке <span>{available ? number(orderCount) : '—'}</span></button>
            <button type="button" aria-pressed={scope === 'all'} onClick={() => changeScope('all')} disabled={!available}>Весь расчёт <span>{available ? number(rows.length) : '—'}</span></button>
          </div></div>

          <div className="filters">
            <label className="search-field"><Search size={18} aria-hidden="true" /><span className="sr-only">Поиск по товару или артикулу</span><input type="search" placeholder="Товар или артикул…" value={filters.search} onChange={(event) => setFilter('search', event.target.value)} disabled={!available} /></label>
            <label className="select-field"><span className="sr-only">Поставщик</span><select value={filters.supplier} onChange={(event) => setFilter('supplier', event.target.value)} disabled={!available}><option value="">Все поставщики</option>{suppliers.map((supplier) => <option key={supplier}>{supplier}</option>)}</select></label>
            <label className="select-field"><span className="sr-only">Срочность</span><select value={filters.urgency} onChange={(event) => setFilter('urgency', event.target.value)} disabled={!available}><option value="">Любая срочность</option>{Object.entries(URGENCY).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}</select></label>
            <label className="select-field category-select"><span className="sr-only">Категория</span><select value={filters.category} onChange={(event) => setFilter('category', event.target.value)} disabled={!available}><option value="">Все категории</option>{categories.map((category) => <option key={category}>{category}</option>)}</select></label>
            {hasFilters && <button className="reset-filters" onClick={() => setFilters(INITIAL_FILTERS)}><X size={15} />Сбросить</button>}
          </div>

          {loading ? <div className="loading-state" role="status"><LoaderCircle className="spin" size={25} /><strong>Загружаем рекомендации</strong><p>Получаем результаты расчёта…</p></div>
            : error ? <div className="empty-state error-state" role="alert"><div className="state-icon"><TriangleAlert size={29} strokeWidth={1.6} /></div><h3>Не удалось получить рекомендации</h3><p>Ошибка при загрузке данных</p><div className="empty-actions"><button className="button button-primary" onClick={() => setReload((count) => count + 1)}><RefreshCw size={16} />Повторить</button></div></div>
            : rows.length === 0 ? <div className="empty-state"><div className="state-icon"><ClipboardList size={29} /></div><h3>Расчёт пока без рекомендаций</h3><p>Сервер вернул пустой список. После подготовки данных обновите страницу.</p><button className="button button-outline" onClick={() => setReload((count) => count + 1)}><RefreshCw size={16} />Обновить</button></div>
            : visibleRows.length === 0 ? <div className="empty-state"><div className="state-icon"><Search size={29} /></div><h3>Нет товаров по этим фильтрам</h3><p>В расчёте {rows.length} позиций. Измените запрос или сбросьте фильтры.</p><button className="button button-outline" onClick={() => setFilters(INITIAL_FILTERS)}>Сбросить фильтры</button></div>
            : <>
              <div className="table-scroll" tabIndex={0} role="region" aria-label="Таблица рекомендаций, можно прокручивать по горизонтали">
                <table><caption className="sr-only">Рекомендации по закупкам. Нажмите на название товара, чтобы посмотреть обоснование.</caption><thead><tr><th scope="col" className="product-column">Товар / артикул</th><th scope="col">Поставщик</th><th scope="col" className="numeric">Остаток</th><th scope="col" className="numeric">В пути</th><th scope="col" className="numeric">Запас, дн.</th><th scope="col" className="numeric order-column">К заказу</th><th scope="col">Приоритет</th><th scope="col"><span className="sr-only">Подробнее</span></th></tr></thead>
                  <tbody>{pageData.rows.map((row) => <tr key={row.id} className={row.urgency === 'critical' ? 'row-critical' : ''}>
                    <td className="product-cell"><button className="product-link" onClick={() => setSelected(row)}>{row.product_name}</button><div className="product-meta"><span className="mono">{row.sku}</span><span className="meta-dot">·</span><span>{row.category}</span>{mode !== 'demo' && row.synthetic && <span className="synthetic-tag">Синтетика</span>}</div></td>
                    <td><Supplier name={row.supplier} /></td><td className="numeric">{number(row.stock_qty)} <span className="unit">{row.unit}</span></td><td className={`numeric ${row.in_transit_qty === 0 ? 'muted' : 'transit-value'}`}>{row.in_transit_qty === 0 ? '0' : `+${number(row.in_transit_qty)}`}</td>
                    <td className="numeric"><span className={row.coverage_days !== null && row.lead_time_days !== null && row.coverage_days < row.lead_time_days ? 'coverage-risk' : ''}>{number(row.coverage_days)}</span></td>
                    <td className="numeric order-value">{number(row.recommended_order_qty)} <span className="unit">{row.unit}</span></td><td><UrgencyBadge value={row.urgency} /></td><td><button className="row-details" aria-label={`Обоснование: ${row.product_name}`} onClick={() => setSelected(row)}><ArrowUpRight size={18} /></button></td>
                  </tr>)}</tbody></table>
              </div>
              <div className="table-footer"><span>Показано <strong>{pageData.start}-{pageData.end}</strong> из {visibleRows.length} позиций</span><div className="pagination" aria-label="Страницы таблицы"><button type="button" className="page-button" aria-label="Предыдущая страница" title="Предыдущая страница" disabled={pageData.currentPage === 1} onClick={() => setPage(pageData.currentPage - 1)}><ChevronLeft size={18} /></button><span aria-live="polite">{pageData.currentPage} / {pageData.totalPages}</span><button type="button" className="page-button" aria-label="Следующая страница" title="Следующая страница" disabled={pageData.currentPage === pageData.totalPages} onClick={() => setPage(pageData.currentPage + 1)}><ChevronRight size={18} /></button></div><label className="sort-control"><SlidersHorizontal size={15} /><span className="sr-only">Сортировка</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option value="priority">По приоритету</option><option value="quantity">По количеству к заказу</option><option value="original">Порядок backend</option></select></label></div>
            </>}
        </section>
        {available && <div className="bottom-notes"><span>Выгрузка учитывает фильтры</span></div>}
        <footer className="page-footer"><span>KETNAVR TEAM</span></footer>
      </main>
    </div>
    <DetailDialog row={selected} onClose={() => setSelected(null)} mode={mode} />
  </div>;
}
