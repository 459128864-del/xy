# ETF Rotation V6

一个面向研究的 ETF 多因子轮动与无未来函数回测项目。V6 将动量质量、
市场状态、仓位约束和组合级回撤控制拆成独立模块，所有参数集中在 YAML 配置中。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests
python scripts/run_backtest.py
python scripts/generate_report.py
```

## 研究约束

- 信号只使用当日及以前的数据，下一交易日持仓生效。
- 回测计入单边交易成本，并限制单标的和组合总暴露。
- 市场状态分为进攻、均衡、防守，低置信阶段主动保留现金。
- 示例数据只验证机制，不代表真实历史业绩。

详细规则见 [策略说明](docs/strategy_v6.md) 与
[回测规则](docs/backtest_rules.md)。

> 本项目仅用于研究和教育，不构成投资建议。
