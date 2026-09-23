import test from 'node:test';
import assert from 'node:assert/strict';
import { askAssistant } from '../src/lib/api.js';

test('assistant posts bounded dialogue and returns a trimmed answer', async () => {
  const history = [{ role: 'user', content: 'Какие риски?' }];
  const answer = await askAssistant({ question: 'А сумма?', history, fetchImpl: async (url, options) => {
    assert.equal(url, '/api/assistant/chat');
    assert.equal(options.method, 'POST');
    assert.equal(options.cache, 'no-store');
    assert.equal(options.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(options.body), { question: 'А сумма?', history });
    return Response.json({ answer: '  Сумма неполная.  ' });
  } });
  assert.equal(answer, 'Сумма неполная.');
});

test('assistant preserves safe server messages for unavailable AI and rate limits', async () => {
  for (const status of [429, 502, 503]) {
    await assert.rejects(askAssistant({ question: 'Вопрос', fetchImpl: async () =>
      Response.json({ detail: 'Попробуйте позже.' }, { status }) }), /Попробуйте позже/);
  }
});

test('an older backend without chat gives an actionable message', async () => {
  for (const status of [404, 405]) {
    await assert.rejects(askAssistant({ question: 'Вопрос', fetchImpl: async () =>
      new Response('<html>Not found</html>', { status }) }), /ещё не подключён/);
  }
});

test('assistant rejects empty or malformed successful responses', async () => {
  for (const data of [{}, { answer: '' }, { answer: '  ' }, { answer: 12 }]) {
    await assert.rejects(askAssistant({ question: 'Вопрос', fetchImpl: async () => Response.json(data) }), /пустой ответ/);
  }
  await assert.rejects(askAssistant({ question: 'Вопрос', fetchImpl: async () => new Response('<html>') }), /пустой ответ/);
});

test('assistant connection failures do not invent a response', async () => {
  await assert.rejects(askAssistant({ question: 'Вопрос', fetchImpl: async () => { throw new TypeError('Failed to fetch'); } }), /Нет соединения/);
});

test('assistant timeout is 30 seconds without retrying paid requests', async t => {
  let calls = 0;
  t.mock.method(AbortSignal, 'timeout', ms => {
    assert.equal(ms, 30000);
    return AbortSignal.abort(new DOMException('Timeout', 'TimeoutError'));
  });
  await assert.rejects(askAssistant({ question: 'Вопрос', fetchImpl: async (_url, options) => {
    calls++;
    throw options.signal.reason;
  } }), /30 секунд/);
  assert.equal(calls, 1);
});

test('assistant preserves caller cancellation', async () => {
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(askAssistant({ question: 'Вопрос', signal: controller.signal,
    fetchImpl: async (_url, options) => { throw options.signal.reason; } }), { name: 'AbortError' });
});
