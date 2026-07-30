const state = { scan: [], quotes: {}, category: "全部", liquidity: 1e8 };
const $ = (id) => document.getElementById(id);
const pct = (x) => Number.isFinite(x) ? `${x >= 0 ? "+" : ""}${(x * 100).toFixed(2)}%` : "—";
const money = (x) => !Number.isFinite(x) ? "—" : x >= 1e8 ? `${(x / 1e8).toFixed(1)}亿` : `${(x / 1e4).toFixed(0)}万`;
const price = (x) => Number.isFinite(x) ? x.toFixed(x >= 100 ? 2 : 3) : "—";
const esc = (x) => String(x).replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;" }[c]));

function renderCategories() {
  const cats = ["全部", ...new Set(state.scan.map((x) => x.category))];
  $("categories").innerHTML = cats.map((x) =>
    `<button class="${x === state.category ? "active" : ""}" data-category="${esc(x)}">${esc(x)}</button>`
  ).join("");
  $("categories").querySelectorAll("button").forEach((button) => button.onclick = () => {
    state.category = button.dataset.category;
    renderCategories();
    renderRows();
  });
}

function renderRows() {
  const visible = state.scan.filter((x) =>
    (state.category === "全部" || x.category === state.category) &&
    (x.factor.avgAmount20 || 0) >= state.liquidity
  );
  $("rows").innerHTML = visible.length ? visible.map((x, i) => {
    const q = state.quotes[x.code] || {};
    const dayClass = q.changePct > 0 ? "up" : q.changePct < 0 ? "down" : "";
    const scoreClass = x.score >= 70 ? "hot" : x.score >= 50 ? "warm" : "";
    return `<tr>
      <td><span class="rank ${i < 3 ? "top" : ""}">${i + 1}</span></td>
      <td><strong>${esc(x.name)}</strong><small>${x.code} · ${esc(x.category)} · ${esc(x.historySource || "日线")}</small></td>
      <td class="mono">${price(q.price ?? x.factor.lastClose)}</td>
      <td class="mono ${dayClass}">${Number.isFinite(q.changePct) ? `${q.changePct >= 0 ? "+" : ""}${q.changePct.toFixed(2)}%` : "—"}</td>
      <td><span class="score ${scoreClass}">${x.trendScore.toFixed(1)}</span><small>动能 ${x.score.toFixed(1)}</small></td>
      <td><span class="phase phase-${x.phase}">${x.phase}</span></td>
      <td><span class="action action-${x.advice.tone}">${esc(x.advice.action)}</span><small>置信度 ${x.advice.confidence}</small></td>
      <td class="boundary">${esc(x.advice.trigger)}</td>
      <td class="boundary">${esc(x.advice.invalidation)}</td>
      <td class="mono">${pct(x.factor.ret20)}</td>
      <td class="mono">${pct(x.factor.ret60)}</td>
    </tr>`;
  }).join("") : `<tr><td colspan="11" class="loading">当前筛选条件下没有ETF</td></tr>`;
}

function renderPortfolio(data) {
  const portfolio = data.modelPortfolio;
  if (!portfolio) return;
  $("portfolioRationale").textContent = portfolio.rationale;
  const cards = portfolio.positions.map((x) => `
    <article class="portfolioCard">
      <div class="weightRing" style="--weight:${x.weight * 3.6}deg"><strong>${x.weight}%</strong></div>
      <div class="portfolioInfo">
        <div><h3>${esc(x.name)}</h3><span>${x.code} · ${esc(x.category)} · ${esc(x.phase)}</span></div>
        <p>${esc(x.reason)}</p>
        <small><b>确认：</b>${esc(x.trigger)}</small>
        <small><b>失效：</b>${esc(x.invalidation)}</small>
      </div>
    </article>`).join("");
  $("portfolioCards").innerHTML = cards + `
    <article class="portfolioCard cashCard">
      <div class="weightRing cashRing" style="--weight:${portfolio.cashWeight * 3.6}deg"><strong>${portfolio.cashWeight}%</strong></div>
      <div class="portfolioInfo"><div><h3>现金 / 等待</h3><span>风险缓冲</span></div>
      <p>没有合格趋势时不强行配置；为后续确认信号和组合轮换保留主动权。</p></div>
    </article>`;
  const reminders = data.rotationReminders || [];
  $("reminderBadge").textContent = reminders.length ? `● ${reminders.length} 条轮换提醒` : "✓ 当前组合无需更换";
  $("reminderBadge").className = `reminderBadge ${reminders.length ? "hasAlerts" : "clear"}`;
  document.title = reminders.length ? `● (${reminders.length}) ETF 动能雷达` : "ETF 动能雷达";
  $("rotationAlerts").innerHTML = reminders.map((x) =>
    `<div class="rotationAlert alert-${x.level}"><strong>${esc(x.title)}</strong><span>${esc(x.reason)}</span></div>`
  ).join("");
}

function renderMarketBreadth(data) {
  $("marketBreadth").innerHTML = (data.marketBreadth || []).map((x) => `
    <article>
      <div><strong>${esc(x.name)}</strong><small>${x.code} · ${esc(x.basis)}</small></div>
      <span class="breadth-${x.signal}">${esc(x.signal)}</span>
      <b class="mono">${Number.isFinite(x.change) ? pct(x.change) : "—"}</b>
    </article>
  `).join("");
}

async function loadScan(force = false) {
  $("refresh").disabled = true;
  $("refresh").textContent = "计算中…";
  try {
    const response = await fetch(`/api/scan${force ? "?force=1" : ""}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    state.scan = data.rows;
    $("regime").textContent = data.regime;
    $("regime").className = `regime-${data.regime}`;
    $("universeCount").textContent = data.rows.length;
    $("leader").textContent = data.rows[0]?.name || "—";
    $("leaderScore").textContent = data.rows[0] ? `综合分 ${data.rows[0].trendScore} · 原始动能 ${data.rows[0].score}` : "综合动能";
    $("exposure").textContent = data.allocationGuide?.exposure || "—";
    $("exposureNote").textContent = data.allocationGuide?.note || "按市场状态调整";
    const lead = data.rows[0];
    if (lead) {
      $("decisionTitle").textContent = `${lead.name} · ${lead.phase}`;
      $("decisionReason").textContent = `${lead.advice.rationale}；${lead.advice.riskBudget}。`;
      $("decisionAction").textContent = lead.advice.action;
      $("decisionAction").className = `text-${lead.advice.tone}`;
      $("decisionTrigger").textContent = lead.advice.trigger;
      $("decisionInvalidation").textContent = lead.advice.invalidation;
    }
    renderMarketBreadth(data);
    renderPortfolio(data);
    renderCategories();
    renderRows();
  } catch (error) {
    $("rows").innerHTML = `<tr><td colspan="11" class="loading error">${esc(error.message || "因子计算失败")}</td></tr>`;
  } finally {
    $("refresh").disabled = false;
    $("refresh").textContent = "重算因子";
  }
}

async function loadQuotes() {
  try {
    const response = await fetch("/api/quotes");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    state.quotes = data.quotes;
    $("liveDot").classList.add("online");
    $("statusText").textContent = "实时行情已连接";
    $("updatedAt").textContent = new Date(data.at).toLocaleTimeString("zh-CN", { hour12: false });
    renderRows();
  } catch {
    $("liveDot").classList.remove("online");
    $("statusText").textContent = "行情暂时中断";
  }
}

$("liquidity").onchange = (event) => { state.liquidity = Number(event.target.value); renderRows(); };
$("refresh").onclick = () => loadScan(true);
$("adoptPortfolio").onclick = async () => {
  $("adoptPortfolio").disabled = true;
  $("adoptPortfolio").textContent = "正在同步…";
  try {
    const response = await fetch("/api/portfolio/adopt", { method: "POST" });
    if (!response.ok) throw new Error("同步失败");
    await loadScan();
  } finally {
    $("adoptPortfolio").disabled = false;
    $("adoptPortfolio").textContent = "将目标组合记为当前组合";
  }
};
await Promise.all([loadScan(), loadQuotes()]);
setInterval(loadQuotes, 5000);
setInterval(() => loadScan(false), 5 * 60 * 1000);
