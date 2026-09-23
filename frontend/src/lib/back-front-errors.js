const ERROR_STORAGE_KEY = 'back-front-errors';

export function saveBackFrontError(error, context = {}) {
  const entry = {
    timestamp: new Date().toISOString(),
    message: error?.message || String(error),
    name: error?.name || 'Error',
    context,
  };

  if (typeof window === 'undefined' || !window.localStorage) return entry;

  try {
    const previous = JSON.parse(window.localStorage.getItem(ERROR_STORAGE_KEY) || '[]');
    const history = Array.isArray(previous) ? previous : [];
    window.localStorage.setItem(ERROR_STORAGE_KEY, JSON.stringify([...history, entry].slice(-25)));
  } catch {
    // Error logging must never block the user-facing state.
  }

  return entry;
}


