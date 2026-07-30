import test from "node:test";
import assert from "node:assert/strict";
import { buildAdvice, buildModelPortfolio, pctChange, pathEfficiency, maxDrawdown, calculateRawFactor, scoreUniverse } from "../factors.js";

test("基础收益和路径效率计算正确", () => {
  assert.equal(pctChange([1, 2, 3, 4], 2), 1);
  assert.equal(pathEfficiency([1, 2, 3, 4], 3, 0), 1);
  assert.equal(maxDrawdown([10, 12, 9, 11], 4), -0.25);
});

test("持续上涨ETF应获得正向原始因子", () => {
  const bars = Array.from({ length: 150 }, (_, i) => ({ close: 100 + i, amount: 2e8 }));
  const factor = calculateRawFactor(bars);
  assert.ok(factor.ret20 > 0);
  assert.ok(factor.trend > 0);
  assert.equal(factor.efficiency, 1);
});

test("横截面综合分可排序", () => {
  const make = (base, step) => ({
    code: String(base),
    factor: calculateRawFactor(Array.from({ length: 150 }, (_, i) => ({ close: base + i * step, amount: 2e8 })))
  });
  const result = scoreUniverse([make(100, 1), make(100, 0.2), make(200, -0.2)]);
  assert.equal(result[0].code, "100");
  assert.ok(result[0].score > result.at(-1).score);
});

test("趋势破坏时给出回避建议和明确边界", () => {
  const bars = Array.from({ length: 150 }, (_, i) => ({
    close: i < 100 ? 100 + i * 0.3 : 130 - (i - 100) * 0.8,
    amount: 2e8
  }));
  const item = scoreUniverse([
    { code: "weak", factor: calculateRawFactor(bars) },
    { code: "strong", factor: calculateRawFactor(Array.from({ length: 150 }, (_, i) => ({ close: 100 + i, amount: 2e8 }))) }
  ]).find((x) => x.code === "weak");
  const advice = buildAdvice(item, "防守");
  assert.equal(item.phase, "反转");
  assert.equal(advice.action, "回避");
  assert.match(advice.invalidation, /MA60/);
});

test("防守组合限制ETF总仓位并保留现金", () => {
  const candidate = (code, category, score) => ({
    code, name: code, category, phase: "形成", trendScore: score,
    advice: { tone: "watch", trigger: "突破", invalidation: "跌破" },
    factor: { avgAmount20: 2e8, efficiency20: 0.2, volumeRatio: 1 }
  });
  const portfolio = buildModelPortfolio([
    candidate("bond", "债券", 80), candidate("bank", "金融", 75),
    candidate("broad", "宽基", 70), candidate("tech", "科技", 90)
  ], "防守");
  assert.equal(portfolio.totalExposure, 30);
  assert.equal(portfolio.cashWeight, 70);
  assert.equal(portfolio.positions[0].category, "债券");
});
