# ETF Quant System

一个轻量、可扩展的 ETF 多因子轮动与回测框架。

> 本目录是历史兼容研究框架，不是当前 V6 策略真源。其结果不得标记为 V6 结果，也不得
> 直接解释根目录 JavaScript 雷达建议。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

输入行情使用长表格式，至少包含 `date`、`symbol`、`close` 三列。策略模块负责生成评分，
回测引擎根据调仓日评分选择排名靠前的 ETF，并按等权持有。

```python
import pandas as pd

from backtest.engine import BacktestConfig, run_backtest
from strategy.v12 import v12_signals

prices = pd.read_csv("data/prices.csv", parse_dates=["date"])
signals = v12_signals(prices)
scores = signals[["date", "symbol", "score"]]
result = run_backtest(prices, scores, BacktestConfig(top_n=2))
print(result.metrics)
```

V1.2 输入数据需要 `date`、`symbol`、`high`、`low`、`close`、`volume` 六列。
`v12_signals` 会同时返回五项因子分、综合评分、排名、买卖信号及卖出原因。

## 优化前后回测

优化版保留趋势因子，并增加 ETF 池内波动率过滤及组合最大回撤控制：

```bash
python -m backtest.compare data/prices.csv --output comparison.csv
```

默认过滤年化波动率高于当日 ETF 池 70% 分位的标的；组合从净值高点回撤 8% 时清仓，
并冷却 10 个交易日。输出包括收益率、日胜率、调仓周期胜率、夏普、Sortino、
最大回撤和平均换手率。当前成交语义为T日收盘产生信号、T+1收盘成交、新权重从
T+1至T+2收益区间生效；非调仓日权重自然漂移，空选券执行全现金，成本仅在真实成交日
扣除一次。原始缺失行情不填充；估值层沿用最后收盘价并在恢复日计入完整变化，缺少
原始收盘价时禁止改变该资产权重。

> 本项目仅用于研究和教育，不构成投资建议。
