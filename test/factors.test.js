import test from "node:test";
import assert from "node:assert/strict";
import { buildAdvice, buildModelPortfolio, classifyMarketRegime, pctChange, pathEfficiency, maxDrawdown, calculateRawFactor, scoreUniverse } from "../factors.js";

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
  assert.ok(portfolio.positions.every((position) => position.weight <= 10));
});

test("进攻、均衡和防守组合严格执行单只上限", () => {
  const categories = ["科技", "宽基", "制造", "金融", "债券", "风格"];
  const rows = categories.map((category, index) => ({
    code: String(index), name: category, category, phase: "形成", trendScore: 80 - index,
    advice: { tone: "watch", trigger: "突破", invalidation: "跌破" },
    factor: { avgAmount20: 2e8, efficiency20: 0.2, volumeRatio: 1 }
  }));
  for (const [regime, limit, exposure] of [["进攻", 20, 80], ["均衡", 15, 50], ["防守", 10, 30]]) {
    const portfolio = buildModelPortfolio(rows, regime);
    assert.ok(portfolio.positions.every((position) => position.weight <= limit));
    assert.ok(portfolio.totalExposure <= exposure);
  }
});

test("候选不足时不重新归一化突破单只上限", () => {
  const only = [{
    code: "one", name: "one", category: "科技", phase: "形成", trendScore: 80,
    advice: { tone: "watch", trigger: "突破", invalidation: "跌破" },
    factor: { avgAmount20: 2e8, efficiency20: 0.2, volumeRatio: 1 }
  }];
  assert.equal(buildModelPortfolio(only, "进攻").positions[0].weight, 20);
});

test("未知市场状态保持全现金", () => {
  const portfolio = buildModelPortfolio([], "未知");
  assert.equal(portfolio.totalExposure, 0);
  assert.equal(portfolio.cashWeight, 100);
  assert.deepEqual(portfolio.positions, []);
});

test("实时北证50观察不影响日线市场状态", () => {
  const daily = [
    { signal: "中性", participatesInRegime: true },
    { signal: "中性", participatesInRegime: true },
    { signal: "中性", participatesInRegime: true }
  ];
  assert.equal(classifyMarketRegime([...daily, { signal: "转强", participatesInRegime: false }]), "均衡");
  assert.equal(classifyMarketRegime([...daily, { signal: "转弱", participatesInRegime: false }]), "均衡");
});

test("日线指标不足时市场状态为未知", () => {
  assert.equal(classifyMarketRegime([
    { signal: "转强", participatesInRegime: true },
    { signal: "转强", participatesInRegime: true },
    { signal: "转强", participatesInRegime: false }
  ]), "未知");
});
