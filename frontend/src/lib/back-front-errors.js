import { saveBlob } from './export.js';

const ERROR_STORAGE_KEY = 'back-front-errors';
let sessionHistory;

export function readBackFrontErrors() {
  if (!sessionHistory) {
    sessionHistory = [];
    try {
      const stored = typeof window === 'undefined' ? [] : JSON.parse(window.localStorage.getItem(ERROR_STORAGE_KEY) || '[]');
      if (Array.isArray(stored)) sessionHistory = stored.slice(-25);
    } catch {
      // Private mode, blocked storage or damaged JSON: keep a session-only log.
    }
  }
  return [...sessionHistory];
}

export function saveBackFrontError(error, context = {}) {
  const entry = {
    timestamp: new Date().toISOString(),
    message: error?.message || String(error),
    name: error?.name || 'Error',
    context: Object.fromEntries(['mode', 'endpoint'].filter(key => typeof context[key] === 'string').map(key => [key, context[key]])),
  };

  sessionHistory = [...readBackFrontErrors(), entry].slice(-25);
  try {
    if (typeof window !== 'undefined') window.localStorage.setItem(ERROR_STORAGE_KEY, JSON.stringify(sessionHistory));
  } catch {
    // Error logging must never block the user-facing state.
  }

  return entry;
}

export function downloadBackFrontErrors() {
  saveBlob(new Blob([JSON.stringify(readBackFrontErrors(), null, 2)], { type: 'application/json;charset=utf-8' }), 'back-front-errors.json');
}
