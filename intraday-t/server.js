import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { pressureSignal } from './core.js';

const root = path.dirname(fileURLToPath(import.meta.url));
const data = path.resolve(root, '../data');
const configPath = path.join(data, 'intraday-t-config.json');
fs.mkdirSync(data, { recursive: true });
const demo = !fs.existsSync(configPath);
let config = demo
  ? JSON.parse(fs.readFileSync(path.join(root, 'config.example.json')))
  : JSON.parse(fs.readFileSync(configPath));

function readJson(req, cb) {
  let body = '';
  req.on('data', x => body += x);
  req.on('end', () => {
    try { cb(null, JSON.parse(body || '{}')); }
    catch (err) { cb(err); }
  });
}

const server = http.createServer((req, res) => {
  if (req.method === 'POST' && req.url === '/api/config') {
    readJson(req, (err, value) => {
      res.setHeader('content-type', 'application/json');
      if (err) { res.statusCode = 400; return res.end(JSON.stringify({ ok: false, error: 'invalid json' })); }
      fs.writeFileSync(configPath, JSON.stringify(value, null, 2));
      config = { ...config, ...value };
      res.end(JSON.stringify({ ok: true }));
    });
    return;
  }

  if (req.method === 'POST' && req.url === '/api/pressure-signal') {
    readJson(req, (err, value) => {
      res.setHeader('content-type', 'application/json');
      if (err) { res.statusCode = 400; return res.end(JSON.stringify({ status: 'INVALID', reason: 'invalid json' })); }
      const signal = pressureSignal(value.bars || [], Number(value.pressure), { ...config, ...(value.config || {}) });
      res.end(JSON.stringify(signal));
    });
    return;
  }

  if (req.url === '/api/status') {
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ healthy: true, demo, mode: '研究提醒（不下单）', config }));
    return;
  }

  let file = req.url === '/' ? 'index.html' : req.url.slice(1);
  let p = path.join(root, 'public', file);
  if (!fs.existsSync(p)) { res.statusCode = 404; return res.end('not found'); }
  res.setHeader('content-type', file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'text/javascript' : 'text/html');
  res.end(fs.readFileSync(p));
});

server.listen(config.port, '127.0.0.1', () => console.log(`日内T雷达: http://127.0.0.1:${config.port}${demo ? '（演示模式）' : ''}`));
