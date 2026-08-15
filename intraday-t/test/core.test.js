import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {
  confirmedPivots,
  divergence,
  validateBars,
  tradeGate,
  suggestedQty,
  pressureSignal,
  Replay,
  DailyState,
} from '../core.js';

const cfg = JSON.parse(fs.readFileSync(new URL('../config.example.json', import.meta.url)));
const bar = (i, low = 10, high = 11, volume = 100, difbps = 0, close = 10.5) => ({
  time: `2026-08-12T${String(9 + Math.floor(i / 12)).padStart(2, '0')}:${String(i * 5 % 60).padStart(2, '0')}:00`,
  open: 10,
  high,
  low,
  close,
  volume,
  difbps,
  index: i,
});

test('摆动点等待右侧两根，禁止未来函数', () => {
  let xs = [bar(0, 3), bar(1, 2), bar(2, 1), bar(3, 2), bar(4, 3)];
  assert.equal(confirmedPivots(xs, cfg, 3).lows.length, 0);
  assert.equal(confirmedPivots(xs, cfg, 4).lows[0].confirmedAt, 4);
});

test('标准底背离、近似双底和标准顶背离', () => {
  let a = { index: 1, low: 10, high: 10, volume: 100, difbps: -5 };
  let b = { index: 5, low: 9.9, high: 11, volume: 90, difbps: -2 };
  assert.equal(divergence([a, b], 'bottom', cfg).standard, true);
  b.low = 10.01;
  assert.equal(divergence([a, b], 'bottom', cfg).standard, false);
  a.high = 10;
  b.high = 10.1;
  a.difbps = 5;
  b.difbps = 2;
  assert.equal(divergence([a, b], 'top', cfg).standard, true);
});

test('放量破位、重复乱序与零量安全失败', () => {
  assert.equal(validateBars([bar(0), bar(1, 10, 11, 0)]).ok, false);
  assert.equal(validateBars([bar(1), bar(0)]).ok, false);
  let d = divergence([
    { index: 1, low: 10, volume: 100, difbps: -5 },
    { index: 5, low: 9.9, volume: 130, difbps: -2 },
  ], 'bottom', cfg);
  assert.equal(d.volumeContracted, false);
});

test('RR、毛价差、成本后净价差硬门禁', () => {
  assert.equal(tradeGate({ direction: 'forward', entry: 10, stop: 9.8, target: 10.5, atr20: .2, prevClose: 10, score: .8, cfg }).pass, true);
  assert.ok(tradeGate({ direction: 'forward', entry: 10, stop: 9, target: 10.01, atr20: .2, prevClose: 10, score: .8, cfg }).failures.length);
});

test('100股取整及现金旧仓风险三重约束', () => {
  assert.equal(suggestedQty({ availableOldQty: 5000, cashAvailable: 100000, accountEquity: 1000000, entry: 10, stop: 9, cfg }).qty, 700);
  assert.equal(suggestedQty({ availableOldQty: 5000, cashAvailable: NaN, accountEquity: 1e6, entry: 10, stop: 9, cfg }).qty, null);
});

test('一天一轮、方向锁定及时间门禁', () => {
  let s = new DailyState;
  assert.equal(s.open('A', '2026-01-01', 'forward', '09:39', cfg), false);
  assert.equal(s.open('A', '2026-01-01', 'forward', '10:00', cfg), true);
  assert.equal(s.open('A', '2026-01-01', 'reverse', '10:30', cfg), false);
  s.restore('A', '2026-01-01');
  assert.equal(DailyState.from(s.serialize()).days['2026-01-01:A'].state, 'DONE');
});

test('14:30后不开循环，回放只能逐bar', () => {
  let s = new DailyState;
  assert.equal(s.open('A', 'd', 'forward', '14:31', cfg), false);
  let r = new Replay([bar(0), bar(1)]);
  assert.equal(r.next().length, 1);
  assert.equal(r.future, undefined);
  assert.equal(r.next().length, 2);
});

test('午间休市缺口不会静默填充', () => {
  let xs = [bar(0), { ...bar(1), time: '2026-08-12T13:05:00' }];
  assert.equal(validateBars(xs).ok, true);
  assert.equal(xs.length, 2);
});

function pressureBars(closes, volumes, pressure = 10) {
  return closes.map((close, i) => ({
    time: `2026-08-14T10:${String(i * 5).padStart(2, '0')}:00`,
    open: i ? closes[i - 1] : close,
    high: Math.max(close, pressure * (i >= closes.length - 3 ? 1.002 : .995)),
    low: Math.min(close, pressure * .998),
    close,
    volume: volumes[i],
  }));
}

test('压力位第一根只进入观察，不抢跑', () => {
  const xs = pressureBars([9.8, 9.85, 9.9, 10.02], [100, 100, 100, 160]);
  const signal = pressureSignal(xs, 10, cfg);
  assert.equal(signal.status, 'PRESSURE_WATCH');
});

test('放量突破后下一根守住压力位才确认', () => {
  const xs = pressureBars(
    [9.7, 9.75, 9.8, 9.85, 9.9, 9.95, 10.03, 10.06],
    [100, 100, 100, 100, 100, 100, 180, 150],
  );
  xs.at(-1).low = 10.01;
  const signal = pressureSignal(xs, 10, cfg);
  assert.equal(signal.status, 'BREAKOUT_CONFIRMED');
  assert.equal(signal.confirmationBars, 2);
});

test('刺穿压力但收回下方判为突破失败', () => {
  const xs = pressureBars([9.8, 9.9, 9.98], [100, 100, 150]);
  xs.at(-1).high = 10.06;
  xs.at(-1).close = 9.98;
  const signal = pressureSignal(xs, 10, cfg);
  assert.equal(signal.status, 'BREAKOUT_FAILED');
});

test('三根放量但价格推进弱判为滞涨', () => {
  const xs = pressureBars(
    [9.7, 9.72, 9.74, 9.76, 9.78, 9.8, 9.82, 9.84, 9.86, 9.88, 9.99, 10.00, 10.005],
    [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 160, 170, 180],
  );
  xs.slice(-3).forEach(x => { x.high = 10.02; x.low = 9.98; });
  const signal = pressureSignal(xs, 10, cfg);
  assert.equal(signal.status, 'STALLING');
  assert.ok(signal.volumeRatio >= cfg.pressure_stall_volume_ratio);
});

test('低量站上压力位不误判为突破确认', () => {
  const xs = pressureBars(
    [9.7, 9.75, 9.8, 9.85, 9.9, 9.95, 10.03, 10.04],
    [100, 100, 100, 100, 100, 100, 105, 105],
  );
  xs.at(-1).low = 10.01;
  const signal = pressureSignal(xs, 10, cfg);
  assert.notEqual(signal.status, 'BREAKOUT_CONFIRMED');
});
