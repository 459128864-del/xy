const clamp = (n, min, max) => Math.min(max, Math.max(min, n));

export function pctChange(values, lookback, skip = 0) {
  const end = values.length - 1 - skip;
  const start = end - lookback;
  if (start < 0 || !values[start] || !values[end]) return null;
  return values[end] / values[start] - 1;
}

export function mean(values) {
  const valid = values.filter(Number.isFinite);
  return valid.length ? valid.reduce((a, b) => a + b, 0) / valid.length : null;
}

export function stdev(values) {
  const avg = mean(values);
  if (avg === null || values.length < 2) return null;
  return Math.sqrt(mean(values.map((x) => (x - avg) ** 2)));
}

export function pathEfficiency(values, lookback = 60, skip = 5) {
  const end = values.length - 1 - skip;
  const start = end - lookback;
  if (start < 0) return null;
  let distance = 0;
  for (let i = start + 1; i <= end; i++) distance += Math.abs(values[i] - values[i - 1]);
  return distance ? (values[end] - values[start]) / distance : 0;
}

export function maxDrawdown(values, lookback = 60) {
  const slice = values.slice(-lookback);
  if (slice.length < 2) return null;
  let peak = slice[0];
  let worst = 0;
  for (const value of slice) {
    peak = Math.max(peak, value);
    worst = Math.min(worst, value / peak - 1);
  }
  return worst;
}

export function calculateRawFactor(bars) {
  const closes = bars.map((x) => x.close);
  const amounts = bars.map((x) => x.amount);
  const daily = closes.slice(1).map((x, i) => x / closes[i] - 1);
  const ma20 = mean(closes.slice(-20));
  const ma60 = mean(closes.slice(-60));
  const last = closes.at(-1);
  const previous20High = Math.max(...closes.slice(-21, -1));
  const high60 = Math.max(...closes.slice(-60));
  const low20 = Math.min(...closes.slice(-20));
  const avgAmount5 = mean(amounts.slice(-5));
  const avgAmount20 = mean(amounts.slice(-20));
  const efficiency20 = pathEfficiency(closes, 20, 0);
  const previousEfficiency20 = pathEfficiency(closes.slice(0, -20), 20, 0);
  return {
    ret20: pctChange(closes, 20, 5),
    ret60: pctChange(closes, 60, 5),
    ret120: pctChange(closes, 120, 5),
    efficiency: pathEfficiency(closes, 60, 5),
    efficiency20,
    efficiencyChange: Number.isFinite(previousEfficiency20) ? efficiency20 - previousEfficiency20 : null,
    trend: ma20 && ma60 ? 0.6 * (last / ma20 - 1) + 0.4 * (ma20 / ma60 - 1) : null,
    drawdown: maxDrawdown(closes, 60),
    volatility: stdev(daily.slice(-20)),
    avgAmount20,
    volumeRatio: avgAmount20 ? avgAmount5 / avgAmount20 : null,
    ma20,
    ma60,
    previous20High,
    high60,
    low20,
    distanceToHigh60: last / high60 - 1,
    lastClose: last
  };
}

function percentile(sorted, value) {
  if (!Number.isFinite(value) || sorted.length < 2) return 0.5;
  let below = 0;
  for (const item of sorted) if (item < value) below++;
  return below / (sorted.length - 1);
}

export function scoreUniverse(items) {
  const fields = ["ret20", "ret60", "ret120", "efficiency", "trend", "drawdown", "volatility"];
  const distributions = Object.fromEntries(
    fields.map((field) => [field, items.map((x) => x.factor[field]).filter(Number.isFinite).sort((a, b) => a - b)])
  );
  const scored = items.map((item) => {
    const f = item.factor;
    const p = Object.fromEntries(fields.map((field) => [field, percentile(distributions[field], f[field])]));
    const score = 100 * (
      0.24 * p.ret20 +
      0.22 * p.ret60 +
      0.14 * p.ret120 +
      0.14 * p.efficiency +
      0.12 * p.trend +
      0.09 * p.drawdown +
      0.05 * (1 - p.volatility)
    );
    const trendUp = f.lastClose > f.ma20 && f.ma20 > f.ma60;
    const trendBroken = f.lastClose < f.ma60 && f.ma20 < f.ma60;
    const momentumCooling = f.ret20 < 0 || f.efficiency20 < 0;
    const phase =
      trendBroken && f.ret20 < 0 ? "反转" :
      f.lastClose < f.ma20 && momentumCooling ? "衰竭" :
      trendUp && f.ret20 > 0 && f.efficiency20 > 0.12 && f.volumeRatio >= 0.9 ? "加速" :
      f.lastClose > f.ma60 && f.ma20 >= f.ma60 && (f.efficiencyChange < -0.08 || f.volumeRatio > 1.8) ? "分歧" :
      f.lastClose > f.ma60 && f.ret60 > 0 ? "形成" : "转化";
    return { ...item, score: Math.round(clamp(score, 0, 100) * 10) / 10, phase };
  });

  return scored.map((item) => ({
    ...item,
    trendScore: Math.round(clamp(
      item.score +
      (["形成", "加速"].includes(item.phase) ? 8 : 0) -
      (item.phase === "分歧" ? 4 : 0) -
      (item.phase === "衰竭" ? 16 : 0) -
      (item.phase === "反转" ? 24 : 0),
      0, 100
    ) * 10) / 10
  })).sort((a, b) => b.trendScore - a.trendScore);
}

export function buildAdvice(item, regime = "均衡") {
  const f = item.factor;
  const price = (value) => Number.isFinite(value) ? value.toFixed(value >= 100 ? 2 : 3) : "—";
  const riskBudget = regime === "进攻" ? "组合风险预算可偏高" : regime === "防守" ? "组合风险预算应偏低" : "组合风险预算保持中性";
  let action = "等待确认";
  let tone = "wait";
  let rationale = "趋势与动能证据尚未形成一致方向";
  let trigger = `放量站上 ${price(f.previous20High)}`;
  let invalidation = `收盘跌破 MA60（${price(f.ma60)}）`;

  if (item.phase === "加速" && item.trendScore >= 65) {
    action = regime === "防守" ? "持有 / 不追高" : "持有强势";
    tone = "hold";
    rationale = "多周期动能、均线结构与路径效率共振";
    trigger = `缩量回踩 MA20（${price(f.ma20)}）企稳，或放量突破 ${price(f.previous20High)}`;
    invalidation = `放量跌破 MA20（${price(f.ma20)}），二次确认看 MA60（${price(f.ma60)}）`;
  } else if (item.phase === "形成" && item.trendScore >= 60) {
    action = regime === "防守" ? "观察 / 轻仓试错" : "等待回踩参与";
    tone = "watch";
    rationale = "中期趋势转强，但尚未进入高质量加速";
    trigger = `站稳前高 ${price(f.previous20High)}，且量能比不低于 0.9`;
    invalidation = `收盘跌回 MA60（${price(f.ma60)}）下方`;
  } else if (item.phase === "分歧") {
    action = "保留核心 / 停止加仓";
    tone = "caution";
    rationale = "趋势仍在，但路径效率或量能出现分歧";
    trigger = `重新站稳前高 ${price(f.previous20High)}，路径效率恢复为正`;
    invalidation = `连续两日收在 MA20（${price(f.ma20)}）下方`;
  } else if (item.phase === "衰竭") {
    action = "减仓观察";
    tone = "reduce";
    rationale = "长期动量尚有残留，短期价格结构已经转弱";
    trigger = `重新收复 MA20（${price(f.ma20)}）并出现相对强度回升`;
    invalidation = `跌破 MA60（${price(f.ma60)}）后仍无法快速收复`;
  } else if (item.phase === "反转") {
    action = "回避";
    tone = "avoid";
    rationale = "价格、均线与短期动能共同指向趋势破坏";
    trigger = `先收复 MA60（${price(f.ma60)}），再观察 MA20 上穿`;
    invalidation = `未收复 MA60 前不因超跌改变判断`;
  }

  return {
    action, tone, rationale, trigger, invalidation, riskBudget,
    confidence: ["加速", "反转"].includes(item.phase) ? "高" : ["形成", "衰竭"].includes(item.phase) ? "中" : "低",
    scenarios: {
      strong: `放量突破 ${price(f.previous20High)}：保留强势或在回踩确认后评估参与`,
      neutral: `围绕 MA20（${price(f.ma20)}）震荡：降低交易频率，等待方向`,
      weak: `跌破 MA60（${price(f.ma60)}）：降低风险暴露，等待重新收复`
    }
  };
}

export function buildModelPortfolio(rows, regime = "均衡") {
  const config = regime === "进攻"
    ? { exposure: 80, slots: 4, weights: [0.30, 0.25, 0.25, 0.20], order: ["科技", "宽基", "制造", "金融", "周期", "消费", "跨境", "风格", "商品", "债券"] }
    : regime === "防守"
      ? { exposure: 30, slots: 3, weights: [0.50, 0.30, 0.20], order: ["债券", "金融", "风格", "宽基", "消费", "商品", "跨境", "科技", "周期", "制造"] }
      : { exposure: 50, slots: 4, weights: [0.30, 0.25, 0.25, 0.20], order: ["宽基", "金融", "风格", "消费", "科技", "债券", "商品", "周期", "制造", "跨境"] };

  const eligible = rows.filter((x) =>
    ["形成", "加速"].includes(x.phase) &&
    ["hold", "watch"].includes(x.advice?.tone) &&
    x.trendScore >= 60 &&
    x.factor.avgAmount20 >= 1e8
  );
  const selected = [];
  for (const category of config.order) {
    const candidate = eligible.find((x) => x.category === category && !selected.some((y) => y.code === x.code));
    if (candidate) selected.push(candidate);
    if (selected.length >= config.slots) break;
  }

  const rawWeights = config.weights.slice(0, selected.length);
  const weightTotal = rawWeights.reduce((a, b) => a + b, 0) || 1;
  const positions = selected.map((item, index) => {
    const weight = Math.round(config.exposure * rawWeights[index] / weightTotal);
    const reason = [
      `${item.phase}阶段`,
      `综合分${item.trendScore.toFixed(1)}`,
      item.factor.efficiency20 > 0.12 ? "近期路径效率为正" : "中期趋势已经确认",
      item.factor.volumeRatio >= 0.9 ? "量能获得确认" : "等待量能进一步确认"
    ].join("，");
    return {
      code: item.code, name: item.name, category: item.category, weight,
      phase: item.phase, score: item.trendScore, reason,
      trigger: item.advice.trigger, invalidation: item.advice.invalidation
    };
  });
  const invested = positions.reduce((sum, x) => sum + x.weight, 0);
  return {
    regime,
    positions,
    cashWeight: 100 - invested,
    totalExposure: invested,
    rationale: regime === "防守"
      ? "主要矛盾是市场趋势偏弱与局部强势资产之间的冲突，因此提高现金和防御资产权重。"
      : regime === "进攻"
        ? "市场趋势与强势ETF形成共振，允许提高风险暴露，但仍保留现金应对分歧。"
        : "市场方向尚未完全一致，采用中等仓位并分散在不同驱动类别。"
  };
}
