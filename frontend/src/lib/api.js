import { parseRecommendationsResponse } from './contract.js';

const config = import.meta.env ?? {};
export const API_BASE_URL = (config.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
export const API_PATH = config.VITE_RECOMMENDATIONS_PATH || '/recommendations';
export const DEFAULT_MODE = config.VITE_DATA_MODE === 'demo' ? 'demo' : 'api';

export async function getRecommendations({ mode = 'api', signal, includeNoOrder = false, fetchImpl = globalThis.fetch } = {}) {
  if (mode === 'demo') {
    const { demoResponse } = await import('../data/demo.js');
    return parseRecommendationsResponse(demoResponse);
  }
  if (mode !== 'api') throw new Error('Неизвестный источник данных.');
  let requestUrl = `${API_BASE_URL}${API_PATH}`;
  if (includeNoOrder) {
    const url = new URL(requestUrl, 'http://localhost');
    url.searchParams.set('include_no_order', 'true');
    url.searchParams.set('limit', '0');
    requestUrl = /^https?:\/\//.test(requestUrl) ? url.href : `${url.pathname}${url.search}`;
  }
  const combinedSignal = signal
    ? AbortSignal.any([signal, AbortSignal.timeout(45000)])
    : AbortSignal.timeout(45000);
  try {
    const response = await fetchImpl(requestUrl, {
      headers: { Accept: 'application/json' },
      signal: combinedSignal,
      cache: 'no-store',
    });
    if (!response.ok) throw new Error(`Backend вернул HTTP ${response.status}. Проверьте его запуск и адрес API.`);
    if (!(response.headers.get('content-type') || '').includes('application/json')) {
      throw new Error('API вернул не JSON. Проверьте адрес endpoint и настройку proxy.');
    }
    return parseRecommendationsResponse(await response.json());
  } catch (error) {
    if (signal?.aborted) throw error;
    if (combinedSignal.aborted) throw new Error('Backend не ответил за 45 секунд. Повторите запрос.');
    if (error instanceof TypeError) throw new Error('Нет соединения с backend. Проверьте адрес API и доступность сервера.');
    throw error;
  }
}

export async function askAssistant({ question, history = [], signal, fetchImpl = globalThis.fetch }) {
  const combinedSignal = signal
    ? AbortSignal.any([signal, AbortSignal.timeout(30000)])
    : AbortSignal.timeout(30000);
  try {
    const response = await fetchImpl(`${API_BASE_URL}/assistant/chat`, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history }),
      signal: combinedSignal,
      cache: 'no-store',
    });
    const data = (response.headers.get('content-type') || '').includes('application/json')
      ? await response.json() : null;
    if (!response.ok) {
      if (response.status === 404 || response.status === 405) {
        throw new Error('Помощник ещё не подключён на сервере.');
      }
      throw new Error(typeof data?.detail === 'string' ? data.detail : `Ошибка сервера: HTTP ${response.status}`);
    }
    if (typeof data?.answer !== 'string' || !data.answer.trim()) {
      throw new Error('Помощник вернул пустой ответ. Попробуйте ещё раз.');
    }
    return data.answer.trim();
  } catch (error) {
    if (signal?.aborted) throw error;
    if (combinedSignal.aborted) throw new Error('Помощник не ответил за 30 секунд. Повторите запрос.');
    if (error instanceof TypeError) throw new Error('Нет соединения с backend. Проверьте запуск сервера.');
    throw error;
  }
}


