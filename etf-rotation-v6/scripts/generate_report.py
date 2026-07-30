#!/usr/bin/env python3
"""Render a compact dialectical research report from backtest metrics."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
metrics = json.loads((ROOT / "backtests/baseline_metrics.json").read_text())

report = f"""# ETF Rotation V6 基线报告

## 一句话判断

当前样本仅用于验证机制，证据强度低；策略可以运行，但不能据此判断真实收益能力。

## 主要矛盾

趋势轮动需要承担波动捕捉持续性，而仓位上限、市场状态降仓和回撤冷却会牺牲部分弹性。

## 客观结果

- 总收益：{metrics['total_return']:.2%}
- 年化波动率：{metrics['annualized_volatility']:.2%}
- 夏普：{metrics['sharpe']:.2f}
- 最大回撤：{metrics['max_drawdown']:.2%}
- 平均换手率：{metrics['average_turnover']:.2%}

## 三种情景

| 情景 | 触发条件 | 研究应对 | 失效条件 |
|---|---|---|---|
| 强势 | 样本外收益、夏普和回撤均优于基线 | 保留参数，扩大滚动验证 | 多窗口优势反转 |
| 中性 | 回撤受控但收益优势不稳定 | 降低调仓频率，检查成本敏感性 | 风险调整收益持续为负 |
| 弱势 | 收益和夏普下降且回撤扩大 | 停止参数优化，重查因子有效性 | 新样本恢复稳定优势 |

## 改变观点的证据

五年以上复权数据、严格样本外检验和包含存续偏差的 ETF 池会改变当前判断。

## 风险提示

本报告是研究辅助，不构成收益承诺或投资建议。
"""

(ROOT / "backtests/baseline_report.md").write_text(report, encoding="utf-8")
print(ROOT / "backtests/baseline_report.md")
