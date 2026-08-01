import http from "node:http";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { buildAdvice, buildModelPortfolio, calculateRawFactor, classifyMarketRegime, scoreUniverse } from "./factors.js";

const root = fileURLToPath(new URL(".", import.meta.url));
const port = Number(process.env.PORT || 8787);
const portfolioFile = join(root, "data", "current-portfolio.json");

const ETF_UNIVERSE = [
  ["510300", "沪深300", "宽基"], ["510500", "中证500", "宽基"], ["512100", "中证1000", "宽基"],
  ["588000", "科创50", "宽基"], ["159915", "创业板", "宽基"], ["510050", "上证50", "宽基"],
  ["510880", "红利ETF", "风格"], ["515180", "红利低波", "风格"], ["512890", "红利低波100", "风格"],
  ["512480", "半导体", "科技"], ["515030", "新能源车", "制造"], ["512660", "军工", "制造"],
  ["512760", "芯片", "科技"], ["515050", "5G通信", "科技"], ["512720", "计算机", "科技"],
  ["512800", "银行", "金融"], ["512070", "证券保险", "金融"], ["512010", "医药", "消费"],
  ["159928", "消费", "消费"], ["515220", "煤炭", "周期"], ["512400", "有色金属", "周期"],
  ["518880", "黄金", "商品"], ["513100", "纳指", "跨境"], ["513500", "标普500", "跨境"],
  ["513060", "恒生医疗", "跨境"], ["513330", "恒生互联网", "跨境"], ["511010", "国债", "债券"]
].map(([code, name, category]) => ({ code, name, category, market: code.startsWith("5") ? 1 : 0 }));

const cache = { scan: null, scanAt: 0, quotes: null, quotesAt: 0 };
const json = (res, status, body) => {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
  res.end(JSON.stringify(body));
};

async function fetchJson(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { Referer: "https://quote.eastmoney.com/", "User-Agent": "ETF-Momentum-Radar/0.1" }
    });
    if (!response.ok) throw new Error(`行情源返回 ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function getHistory(etf) {
  try {
    const params = new URLSearchParams({
      secid: `${etf.market}.${etf.code}`, klt: "101", fqt: "1", lmt: "260",
      end: "20500101", fields1: "f1,f2,f3,f4,f5,f6",
      fields2: "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    });
    const payload = await fetchJson(`https://push2his.eastmoney.com/api/qt/stock/kline/get?${params}`);
    const lines = payload?.data?.klines || [];
    if (lines.length < 130) throw new Error("主日线源数据不足");
    return {
      source: "东方财富",
      bars: lines.map((line) => {
        const [date, open, close, high, low, volume, amount] = line.split(",");
        return { date, open: +open, close: +close, high: +high, low: +low, volume: +volume, amount: +amount };
      }).filter((x) => Number.isFinite(x.close))
    };
  } catch {
    const symbol = `${etf.market === 1 ? "sh" : "sz"}${etf.code}`;
    const payload = await fetchJson(`https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${symbol},day,,,260,qfq`);
    const node = payload?.data?.[symbol];
    const lines = node?.qfqday || node?.day || [];
    if (lines.length < 130) throw new Error("主备日线源均不可用");
    return {
      source: "腾讯财经备用源",
      bars: lines.map(([date, open, close, high, low, volume]) => ({
        date, open: +open, close: +close, high: +high, low: +low,
        volume: +volume, amount: +volume * +close * 100
      })).filter((x) => Number.isFinite(x.close))
    };
  }
}

async function getQuotes() {
  if (cache.quotes && Date.now() - cache.quotesAt < 4000) return cache.quotes;
  const secids = ETF_UNIVERSE.map((x) => `${x.market}.${x.code}`).join(",");
  const params = new URLSearchParams({
    secids, fields: "f12,f14,f2,f3,f4,f5,f6,f15,f16,f17,f18", fltt: "2"
  });
  const payload = await fetchJson(`https://push2.eastmoney.com/api/qt/ulist.np/get?${params}`);
  const quotes = Object.fromEntries((payload?.data?.diff || []).map((x) => [x.f12, {
    price: x.f2, changePct: x.f3, change: x.f4, volume: x.f5, amount: x.f6,
    high: x.f15, low: x.f16, open: x.f17, previousClose: x.f18
  }]));
  cache.quotes = quotes;
  cache.quotesAt = Date.now();
  return quotes;
}

async function getNorth50Snapshot() {
  try {
    const params = new URLSearchParams({
      secid: "0.899050", fltt: "2", fields: "f43,f44,f45,f46,f47,f48,f57,f58,f60"
    });
    const payload = await fetchJson(`https://push2.eastmoney.com/api/qt/stock/get?${params}`);
    const data = payload?.data;
    if (!data?.f43 || !data?.f60) return null;
    return {
      code: "899050", name: "北证50", price: data.f43,
      previousClose: data.f60, changePct: (data.f43 / data.f60 - 1) * 100,
      high: data.f44, low: data.f45, open: data.f46, amount: data.f48
    };
  } catch {
    try {
      const payload = await fetchJson("https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param=bj899050,day,,,2");
      const quote = payload?.data?.bj899050?.qt?.bj899050;
      if (!quote?.[3] || !quote?.[4]) return null;
      return {
        code: "899050", name: "北证50", price: +quote[3],
        previousClose: +quote[4], changePct: (+quote[3] / +quote[4] - 1) * 100,
        high: +quote[33], low: +quote[34], open: +quote[5], amount: null
      };
    } catch {
      return null;
    }
  }
}

async function readCurrentPortfolio() {
  try {
    return JSON.parse(await readFile(portfolioFile, "utf8"));
  } catch {
    return null;
  }
}

async function saveCurrentPortfolio(portfolio) {
  await mkdir(join(root, "data"), { recursive: true });
  const saved = { adoptedAt: new Date().toISOString(), regime: portfolio.regime, positions: portfolio.positions, cashWeight: portfolio.cashWeight };
  await writeFile(portfolioFile, JSON.stringify(saved, null, 2));
  return saved;
}

function comparePortfolios(current, target, rows) {
  if (!current) return [];
  const currentMap = new Map(current.positions.map((x) => [x.code, x]));
  const targetMap = new Map(target.positions.map((x) => [x.code, x]));
  const rowMap = new Map(rows.map((x) => [x.code, x]));
  const reminders = [];
  for (const held of current.positions) {
    const targetPosition = targetMap.get(held.code);
    const row = rowMap.get(held.code);
    if (!targetPosition) {
      reminders.push({
        level: row && ["衰竭", "反转"].includes(row.phase) ? "urgent" : "change",
        code: held.code, title: `考虑移出 ${held.name}`,
        reason: row ? `当前阶段已变为${row.phase}，目标组合不再包含该ETF` : "已不在当前目标组合中"
      });
    } else if (Math.abs(targetPosition.weight - held.weight) >= 3) {
      reminders.push({
        level: "adjust", code: held.code, title: `调整 ${held.name} 仓位`,
        reason: `当前记录 ${held.weight}%，模型目标 ${targetPosition.weight}%`
      });
    }
  }
  for (const targetPosition of target.positions) {
    if (!currentMap.has(targetPosition.code)) {
      reminders.push({
        level: "new", code: targetPosition.code, title: `候选替换：${targetPosition.name}`,
        reason: `${targetPosition.phase}阶段，综合分${targetPosition.score.toFixed(1)}`
      });
    }
  }
  if (Math.abs((current.cashWeight ?? 0) - target.cashWeight) >= 5) {
    reminders.push({
      level: "adjust", code: "CASH", title: "调整现金仓位",
      reason: `当前记录 ${current.cashWeight}% ，模型目标 ${target.cashWeight}%`
    });
  }
  return reminders;
}

async function getScan(force = false) {
  if (!force && cache.scan && Date.now() - cache.scanAt < 15 * 60_000) return cache.scan;
  const rows = [];
  const queue = [...ETF_UNIVERSE];
  const workers = Array.from({ length: 5 }, async () => {
    while (queue.length) {
      const etf = queue.shift();
      try {
        const history = await getHistory(etf);
        if (history.bars.length >= 130) rows.push({
          ...etf, factor: calculateRawFactor(history.bars),
          asOf: history.bars.at(-1).date, historySource: history.source
        });
      } catch (error) {
        rows.push({ ...etf, error: error.message });
      }
    }
  });
  await Promise.all(workers);
  const scored = scoreUniverse(rows.filter((x) => x.factor));
  const north50 = await getNorth50Snapshot();
  const benchmarkDefs = [
    ["510300", "沪深300"], ["588000", "科创50"], ["159915", "创业板"]
  ];
  const marketBreadth = benchmarkDefs.map(([code, name]) => {
    const item = scored.find((x) => x.code === code);
    const signal = !item ? "未知" :
      item.factor.lastClose > item.factor.ma60 && item.factor.ret20 > 0 ? "转强" :
      item.factor.lastClose < item.factor.ma60 && item.factor.ret20 < 0 ? "转弱" : "中性";
    return { code, name, signal, phase: item?.phase || "未知", change: item?.factor.ret20 ?? null, basis: "20/60日趋势", participatesInRegime: true };
  });
  marketBreadth.push({
    code: "899050", name: "北证50",
    signal: !north50 ? "未知" : north50.changePct > 0.3 ? "转强" : north50.changePct < -0.3 ? "转弱" : "中性",
    phase: "实时监测", change: north50 ? north50.changePct / 100 : null,
    basis: "实时观察（不参与状态判定）", participatesInRegime: false
  });
  const regime = classifyMarketRegime(marketBreadth);
  const valid = scored.map((item) => ({ ...item, advice: buildAdvice(item, regime) }));
  const modelPortfolio = buildModelPortfolio(valid, regime);
  const currentPortfolio = await readCurrentPortfolio();
  const rotationReminders = comparePortfolios(currentPortfolio, modelPortfolio, valid);
  const allocationGuide = regime === "进攻"
    ? { exposure: "50%–80%", single: "单只ETF原则上不超过20%", note: "允许持有强势，但不追单日脉冲" }
    : regime === "防守"
      ? { exposure: "0%–30%", single: "单只ETF原则上不超过10%", note: "现金、债券及等待的权重更高" }
      : regime === "均衡"
        ? { exposure: "30%–50%", single: "单只ETF原则上不超过15%", note: "分批参与，只增加已确认的趋势" }
        : { exposure: "0%", single: "不建立新仓", note: "信息不足，保持现金并等待日线信号完整" };
  cache.scan = {
    generatedAt: new Date().toISOString(), regime, marketBreadth, north50, allocationGuide, rows: valid,
    modelPortfolio, currentPortfolio, rotationReminders,
    failed: rows.filter((x) => x.error).map(({ code, name, error }) => ({ code, name, error }))
  };
  cache.scanAt = Date.now();
  return cache.scan;
}

const mime = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8" };
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);
    if (url.pathname === "/api/quotes") return json(res, 200, { at: new Date().toISOString(), quotes: await getQuotes() });
    if (url.pathname === "/api/scan") return json(res, 200, await getScan(url.searchParams.get("force") === "1"));
    if (url.pathname === "/api/portfolio/adopt" && req.method === "POST") {
      const scan = await getScan();
      scan.currentPortfolio = await saveCurrentPortfolio(scan.modelPortfolio);
      scan.rotationReminders = [];
      return json(res, 200, { ok: true, currentPortfolio: scan.currentPortfolio });
    }
    if (url.pathname === "/api/health") return json(res, 200, { ok: true, source: "eastmoney-public", universe: ETF_UNIVERSE.length });
    const relative = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\/+/, "");
    if (!["index.html", "app.js", "styles.css"].includes(relative)) return json(res, 404, { error: "Not found" });
    const body = await readFile(join(root, "public", relative));
    res.writeHead(200, { "Content-Type": mime[extname(relative)] || "application/octet-stream" });
    res.end(body);
  } catch (error) {
    json(res, 502, { error: error.name === "AbortError" ? "行情源请求超时" : error.message });
  }
});

server.listen(port, "127.0.0.1", () => {
  console.log(`ETF 动能雷达已启动：http://127.0.0.1:${port}`);
});
