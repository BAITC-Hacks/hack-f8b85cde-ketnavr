// Isolated manual UI checks. Never imported by the app or used by production.
// Start with: node tests/qa-server.mjs (localhost:5174 only).
// Select a fixture with POST /__qa/scenario and body ready|empty|error|invalid|slow.
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { demoResponse } from '../src/data/demo.js';

let scenario = 'error';
let chatScenario = 'ready';
const chatRequests = [];
const scenarios = new Set(['ready', 'empty', 'error', 'invalid', 'slow']);
const server = await createServer({
  configFile: false,
  envDir: false,
  cacheDir: 'node_modules/.vite-qa',
  define: {
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/__qa'),
    'import.meta.env.VITE_RECOMMENDATIONS_PATH': JSON.stringify('/recommendations'),
    'import.meta.env.VITE_DATA_MODE': JSON.stringify('api'),
  },
  plugins: [react(), {
    name: 'isolated-qa-fixtures',
    configureServer(vite) {
      vite.middlewares.use('/__qa/chat-scenario', (req, res) => {
        if (req.method !== 'POST') { res.writeHead(405).end(); return; }
        let body = '';
        req.on('data', chunk => { body += chunk; });
        req.on('end', () => {
          if (!['ready', 'error', 'long', 'slow'].includes(body)) { res.writeHead(400).end(); return; }
          chatScenario = body;
          res.end(body);
        });
      });
      vite.middlewares.use('/__qa/chat-stats', (_req, res) => {
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify(chatRequests));
      });
      vite.middlewares.use('/__qa/assistant/chat', (req, res) => {
        if (req.method !== 'POST') { res.writeHead(405).end(); return; }
        let body = '';
        req.on('data', chunk => { body += chunk; });
        req.on('end', () => {
          const request = JSON.parse(body);
          chatRequests.push({ question: request.question, historyLengths: request.history.map(turn => turn.content.length) });
          res.setHeader('Content-Type', 'application/json');
          if (chatScenario === 'slow') {
            const timer = setTimeout(() => res.end(JSON.stringify({ answer: 'Тестовый ответ с задержкой.' })), 1500);
            res.on('close', () => clearTimeout(timer));
            return;
          }
          if (chatScenario === 'error') { res.writeHead(503).end(JSON.stringify({ detail: 'ИИ-помощник пока не настроен на сервере.' })); return; }
          res.end(JSON.stringify({ answer: chatScenario === 'long' ? 'Тестовый длинный ответ. '.repeat(160) : 'Тестовый ответ: расчёт не изменён, сумма неполная.' }));
        });
      });
      vite.middlewares.use('/__qa/scenario', (req, res) => {
        if (req.method !== 'POST') { res.writeHead(405).end(); return; }
        let body = '';
        req.on('data', chunk => { body += chunk; });
        req.on('end', () => {
          if (!scenarios.has(body)) { res.writeHead(400).end(); return; }
          scenario = body;
          res.writeHead(200).end(scenario);
        });
      });
      vite.middlewares.use('/__qa/recommendations', (_req, res) => {
        const current = scenario;
        if (current === 'slow') {
          const timer = setTimeout(() => { res.writeHead(504).end(); }, 60000);
          res.on('close', () => clearTimeout(timer));
          return;
        }
        if (current === 'error') { res.writeHead(500).end('QA simulated failure'); return; }
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify(current === 'invalid' ? { unexpected: true }
          : current === 'empty' ? { schema_version: '1.0', as_of: demoResponse.as_of, recommendations: [] }
          : { ...demoResponse, recommendations: Array.from({ length: 61 }, (_, i) => ({
              ...demoResponse.recommendations[i % demoResponse.recommendations.length], id: 'QA-' + i,
            })) }));
      });
    },
  }],
  server: { host: '127.0.0.1', port: 5174, strictPort: true },
});
await server.listen();
console.log('Isolated synthetic QA server: http://127.0.0.1:5174 (no real backend calls)');
