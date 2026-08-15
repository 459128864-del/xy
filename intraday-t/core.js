export function ema(xs, n) {
  let a = 2 / (n + 1), v = xs[0] ?? 0;
  return xs.map((x, i) => (v = i ? x * a + v * (1 - a) : x));
}

export function rma(xs, n) {
  let v = xs[0] ?? 0;
  return xs.map((x, i) => (v = i ? (v * (n - 1) + x) / n : x));
}

export function indicators(bars) {
  const c = bars.map(b => b.close), e12 = ema(c, 12), e26 = ema(c, 26);
  const dif = c.map((_, i) => e12[i] - e26[i]), dea = ema(dif, 9);
  let sumPV = 0, sumV = 0;
  return bars.map((b, i) => {
    let tp = (b.high + b.low + b.close) / 3;
    sumPV += tp * b.volume;
    sumV += b.volume;
    let tr = Math.max(
      b.high - b.low,
      i ? Math.abs(b.high - c[i - 1]) : 0,
      i ? Math.abs(b.low - c[i - 1]) : 0,
    );
    return {
      ...b,
      vwap: sumV ? sumPV / sumV : null,
      difbps: c[i] ? 10000 * dif[i] / c[i] : 0,
      histbps: c[i] ? 20000 * (dif[i] - dea[i]) / c[i] : 0,
      tr,
    };
  }).map((b, i, a) => ({ ...b, atr5: rma(a.map(x => x.tr), 14)[i] }));
}

export function confirmedPivots(bars, cfg, asOf = bars.length - 1) {
  let lows = [], highs = [];
  for (let i = cfg.pivot_left; i + cfg.pivot_right <= asOf; i++) {
    let w = bars.slice(i - cfg.pivot_left, i + cfg.pivot_right + 1);
    if (bars[i].low <= Math.min(...w.map(x => x.low))) lows.push({ ...bars[i], index: i, confirmedAt: i + cfg.pivot_right });
    if (bars[i].high >= Math.max(...w.map(x => x.high))) highs.push({ ...bars[i], index: i, confirmedAt: i + cfg.pivot_right });
  }
  return { lows, highs };
}

export function divergence(points, type, cfg) {
  if (points.length < 2) return null;
  let [a, b] = points.slice(-2), gap = b.index - a.index;
  if (gap < cfg.pivot_min_gap_bars || gap > cfg.pivot_max_gap_bars) return null;
  let bottom = type === 'bottom';
  let price = bottom ? b.low <= a.low * (1 + cfg.near_equal_price_tolerance) : b.high >= a.high * (1 - cfg.near_equal_price_tolerance);
  let improve = bottom ? b.difbps - a.difbps : a.difbps - b.difbps;
  let need = Math.max(cfg.macd_min_improvement_bps, .15 * Math.abs(a.difbps));
  if (!price || improve < need) return null;
  return {
    type,
    standard: bottom ? b.low < a.low : b.high > a.high,
    volumeContracted: b.volume <= cfg.volume_contraction_ratio * a.volume,
    first: a,
    second: b,
  };
}

export function validateBars(bars) {
  for (let i = 0; i < bars.length; i++) {
    if (!bars[i].time || bars[i].volume <= 0) return { ok: false, reason: '缺失时间或零成交量' };
    if (i && bars[i].time <= bars[i - 1].time) return { ok: false, reason: '重复或乱序bar' };
  }
  return { ok: true };
}

function avg(xs) {
  return xs.length ? xs.reduce((sum, x) => sum + x, 0) / xs.length : null;
}

/**
 * 压力位确认器只读取已经收盘的 5 分钟 bar。
 * 它是研究/提醒状态，不会直接触发下单或修改 DailyState。
 */
export function pressureSignal(bars, pressure, cfg) {
  const valid = validateBars(bars);
  if (!valid.ok) return { status: 'INVALID', label: '数据异常', reason: valid.reason };
  if (!Number.isFinite(pressure) || pressure <= 0) return { status: 'INVALID', label: '压力位无效', reason: 'pressure 必须为正数' };
  if (!bars.length) return { status: 'WAITING', label: '等待数据', reason: '暂无已收盘5分钟K' };

  const proximity = cfg.pressure_proximity_pct;
  const breakoutBuffer = cfg.pressure_breakout_buffer_pct;
  const holdTolerance = cfg.pressure_hold_tolerance_pct;
  const failureBuffer = cfg.pressure_failure_buffer_pct;
  const lookback = cfg.pressure_volume_lookback_bars;
  const stallWindow = cfg.pressure_stall_window_bars;
  const stallVolumeRatio = cfg.pressure_stall_volume_ratio;
  const stallMaxProgressBps = cfg.pressure_stall_max_progress_bps;
  const breakoutVolumeRatio = cfg.volume_break_ratio;

  const latest = bars.at(-1);
  const prev = bars.at(-2);
  const baselineEnd = Math.max(0, bars.length - Math.max(2, stallWindow));
  const baselineStart = Math.max(0, baselineEnd - lookback);
  const baselineBars = bars.slice(baselineStart, baselineEnd);
  const baselineVolume = avg(baselineBars.map(b => b.volume)) ?? latest.volume;
  const latestVolumeRatio = baselineVolume ? latest.volume / baselineVolume : null;
  const distancePct = (latest.close - pressure) / pressure;

  if (prev) {
    const prevBaselineEnd = bars.length - 2;
    const prevBaselineStart = Math.max(0, prevBaselineEnd - lookback);
    const prevBaselineVolume = avg(bars.slice(prevBaselineStart, prevBaselineEnd).map(b => b.volume)) ?? prev.volume;
    const prevVolumeRatio = prevBaselineVolume ? prev.volume / prevBaselineVolume : null;

    const breakoutClosedAbove = prev.close >= pressure * (1 + breakoutBuffer);
    const breakoutHadVolume = prevVolumeRatio !== null && prevVolumeRatio >= breakoutVolumeRatio;
    const nextBarHeld = latest.low >= pressure * (1 - holdTolerance) && latest.close >= pressure;

    if (breakoutClosedAbove && breakoutHadVolume && nextBarHeld) {
      return {
        status: 'BREAKOUT_CONFIRMED',
        label: '突破确认',
        tone: 'green',
        reason: '突破K收在压力上方且放量，下一根5分钟K继续守住压力位',
        pressure,
        distancePct,
        volumeRatio: prevVolumeRatio,
        confirmationBars: 2,
      };
    }

    const lostAfterBreak = prev.close >= pressure * (1 + breakoutBuffer) && latest.close <= pressure * (1 - failureBuffer);
    if (lostAfterBreak) {
      return {
        status: 'BREAKOUT_FAILED',
        label: '突破失败',
        tone: 'red',
        reason: '前一根曾收上压力位，但下一根重新跌回压力下方',
        pressure,
        distancePct,
        volumeRatio: latestVolumeRatio,
        confirmationBars: 2,
      };
    }
  }

  const recent = bars.slice(-stallWindow);
  if (recent.length >= stallWindow) {
    const touchedPressure = Math.max(...recent.map(b => b.high)) >= pressure * (1 - proximity);
    const recentVolume = avg(recent.map(b => b.volume));
    const volumeRatio = baselineVolume ? recentVolume / baselineVolume : null;
    const priceProgressBps = 10000 * (recent.at(-1).close - recent[0].close) / pressure;
    const notEstablishedAbove = recent.at(-1).close < pressure * (1 + breakoutBuffer);
    const stalled = touchedPressure && notEstablishedAbove && volumeRatio !== null && volumeRatio >= stallVolumeRatio && priceProgressBps <= stallMaxProgressBps;

    if (stalled) {
      return {
        status: 'STALLING',
        label: '放量滞涨',
        tone: 'red',
        reason: '压力区附近成交量明显放大，但连续多根5分钟K的价格推进很弱',
        pressure,
        distancePct,
        volumeRatio,
        priceProgressBps,
        progressEfficiency: volumeRatio ? priceProgressBps / volumeRatio : null,
        confirmationBars: stallWindow,
      };
    }
  }

  const oneBarFailure = latest.high >= pressure && latest.close <= pressure * (1 - failureBuffer);
  if (oneBarFailure) {
    return {
      status: 'BREAKOUT_FAILED',
      label: '突破失败',
      tone: 'red',
      reason: '盘中刺穿压力位，但本根5分钟收盘重新落回压力下方',
      pressure,
      distancePct,
      volumeRatio: latestVolumeRatio,
      confirmationBars: 1,
    };
  }

  const touched = latest.high >= pressure * (1 - proximity) || Math.abs(distancePct) <= proximity;
  const pierced = latest.high >= pressure;
  if (touched || pierced) {
    return {
      status: 'PRESSURE_WATCH',
      label: '压力观察',
      tone: 'yellow',
      reason: pierced ? '已经触及或刺穿压力位，但还缺少下一根5分钟K确认' : '进入压力位附近，先观察，不抢先判断突破或滞涨',
      pressure,
      distancePct,
      volumeRatio: latestVolumeRatio,
      confirmationBars: 1,
    };
  }

  return {
    status: 'BELOW_PRESSURE',
    label: '未到压力区',
    tone: 'neutral',
    reason: '距离压力位仍较远',
    pressure,
    distancePct,
    volumeRatio: latestVolumeRatio,
    confirmationBars: 0,
  };
}

export function roundTripCost(c) {
  return c.buy_commission + c.sell_commission + c.sell_taxes + 2 * c.slippage_rate;
}

export function tradeGate({ direction, entry, stop, target, atr20, prevClose, score, cfg }) {
  let gross = direction === 'forward' ? (target - entry) / entry : (entry - target) / entry;
  let risk = direction === 'forward' ? entry - stop : stop - entry;
  let reward = direction === 'forward' ? target - entry : entry - target;
  let rr = risk > 0 ? reward / risk : -Infinity, cost = roundTripCost(cfg);
  let minGross = Math.max(.008, 4 * cost, .35 * atr20 / prevClose), failures = [];
  if (rr < cfg.min_rr) failures.push('RR不足');
  if (gross < minGross) failures.push('毛价差不足');
  if (gross - cost <= 0) failures.push('成本后净价差不足');
  if (score < cfg.min_score) failures.push('评分不足');
  return { pass: !failures.length, rr, gross, net: gross - cost, minGross, failures };
}

export function suggestedQty({ availableOldQty, cashAvailable, accountEquity, entry, stop, cfg }) {
  if ([availableOldQty, cashAvailable, accountEquity].some(x => !Number.isFinite(x))) return { qty: null, reason: '数量不可计算/不可执行' };
  let q = Math.min(availableOldQty * cfg.max_t_fraction, cashAvailable / entry, accountEquity * cfg.risk_per_trade / Math.abs(entry - stop));
  return { qty: Math.floor(q / cfg.lot_size) * cfg.lot_size };
}

export class Replay {
  constructor(bars) { this.bars = bars; this.cursor = 0; }
  next() { if (this.cursor >= this.bars.length) return null; return this.bars.slice(0, ++this.cursor); }
  get future() { return undefined; }
}

export class DailyState {
  constructor() { this.days = {}; }
  open(symbol, date, direction, time, cfg) {
    let k = `${date}:${symbol}`, s = this.days[k];
    if (s?.done || s?.direction) return false;
    if (time < cfg.no_new_cycle_before || time > cfg.no_new_cycle_after) return false;
    this.days[k] = { direction, state: direction === 'forward' ? 'FORWARD_OPEN' : 'REVERSE_OPEN' };
    return true;
  }
  restore(symbol, date) { let s = this.days[`${date}:${symbol}`]; if (s) s.state = 'DONE'; }
  serialize() { return JSON.stringify(this.days); }
  static from(x) { let s = new DailyState(); s.days = JSON.parse(x || '{}'); return s; }
}
