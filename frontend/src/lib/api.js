import { parseRecommendationsResponse } from './contract.js';

const config = import.meta.env ?? {};
export const API_BASE_URL = (config.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
export const API_PATH = config.VITE_RECOMMENDATIONS_PATH || '/recommendations';
export const DEFAULT_MODE = config.VITE_DATA_MODE === 'demo' ? 'demo' : 'api';

export async function getRecommendations({ mode = 'api', signal, fetchImpl = globalThis.fetch } = {}) {
  if (mode === 'demo') {
    const { demoResponse } = await import('../data/demo.js');
    return parseRecommendationsResponse(demoResponse);
  }
  if (mode !== 'api') throw new Error('Неизвестный источник данных.');
  const combinedSignal = signal
    ? AbortSignal.any([signal, AbortSignal.timeout(10000)])
    : AbortSignal.timeout(10000);
  try {
    const response = await fetchImpl(`${API_BASE_URL}${API_PATH}`, {
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
    if (combinedSignal.aborted) throw new Error('Backend не ответил за 10 секунд. Повторите запрос.');
    if (error instanceof TypeError) throw new Error('Нет соединения с backend. Проверьте адрес API и доступность сервера.');
    throw error;
  }
}

