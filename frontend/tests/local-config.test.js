import test from 'node:test';
import assert from 'node:assert/strict';
import configure from '../vite.config.js';

test('explicit localhost mode overrides tunnel, API URL and demo env without changing files', () => {
  const values = {
    BACKEND_URL: 'https://example.invalid',
    VITE_API_BASE_URL: 'https://example.invalid/api',
    VITE_RECOMMENDATIONS_PATH: '/recommendations?ai=true&limit=120',
    VITE_DATA_MODE: 'demo',
  };
  const previous = Object.fromEntries(Object.keys(values).map(key => [key, process.env[key]]));
  try {
    Object.assign(process.env, values);
    const local = configure({ mode: 'localhost' });
    assert.equal(local.server.proxy['/api'].target, 'http://127.0.0.1:8000');
    assert.equal(local.server.proxy['/api'].rewrite('/api/assistant/chat'), '/assistant/chat');
    assert.equal(JSON.parse(local.define['import.meta.env.VITE_API_BASE_URL']), '/api');
    assert.equal(JSON.parse(local.define['import.meta.env.VITE_RECOMMENDATIONS_PATH']), '/recommendations?ai=false&limit=0');
    assert.equal(JSON.parse(local.define['import.meta.env.VITE_DATA_MODE']), 'api');
    assert.equal(configure({ mode: 'development' }).server.proxy['/api'].target, values.BACKEND_URL);
    assert.equal(process.env.BACKEND_URL, values.BACKEND_URL);
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
});
