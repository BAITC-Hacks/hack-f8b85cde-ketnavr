import test from 'node:test';
import assert from 'node:assert/strict';

function installWindow(t, value) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window');
  Object.defineProperty(globalThis, 'window', { configurable: true, value });
  t.after(() => {
    if (previous) Object.defineProperty(globalThis, 'window', previous);
    else delete globalThis.window;
  });
}

test('blocked localStorage cannot break error handling; log remains in memory', async t => {
  installWindow(t, { get localStorage() { throw new Error('Storage denied'); } });
  const { saveBackFrontError, readBackFrontErrors } = await import('../src/lib/back-front-errors.js?qa=blocked');
  assert.doesNotThrow(() => saveBackFrontError(new Error('HTTP 500'), { mode: 'api' }));
  assert.equal(readBackFrontErrors()[0].message, 'HTTP 500');
});

test('damaged storage is recovered; only 25 recent errors and permitted context fields are saved', async t => {
  let value = '{broken';
  installWindow(t, { localStorage: { getItem: () => value, setItem: (_key, data) => { value = data; } } });
  const { saveBackFrontError, readBackFrontErrors } = await import('../src/lib/back-front-errors.js?qa=bounded');
  for (let i = 0; i < 30; i++) saveBackFrontError(new Error(`Failure ${i}`), { mode: 'api', endpoint: '/recommendations', token: 'must-not-be-saved' });
  const entries = readBackFrontErrors();
  assert.equal(entries.length, 25);
  assert.equal(entries[0].message, 'Failure 5');
  assert.equal(entries[24].message, 'Failure 29');
  assert.deepEqual(entries[0].context, { mode: 'api', endpoint: '/recommendations' });
  assert.deepEqual(JSON.parse(value), entries);
});

test('a download contains the recorded error and uses the requested filename', async t => {
  installWindow(t, { localStorage: { getItem: () => '[]', setItem() {} } });
  let downloadedBlob;
  const anchor = { href: '', download: '', click() {}, remove() {} };
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'document');
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { createElement: () => anchor, body: { append() {} } } });
  t.after(() => { if (previous) Object.defineProperty(globalThis, 'document', previous); else delete globalThis.document; });
  t.mock.method(URL, 'createObjectURL', blob => { downloadedBlob = blob; return 'blob:qa'; });
  t.mock.method(URL, 'revokeObjectURL', () => {});
  t.mock.method(globalThis, 'setTimeout', () => 0);
  const { saveBackFrontError, downloadBackFrontErrors } = await import('../src/lib/back-front-errors.js?qa=download');
  saveBackFrontError(new Error('HTTP 500'));
  downloadBackFrontErrors();
  assert.equal(anchor.download, 'back-front-errors.json');
  assert.equal(JSON.parse(await downloadedBlob.text())[0].message, 'HTTP 500');
});
