# V6.0 阻断验证测试结果

> 工程验证，不代表真实投资效果。
>
> 本记录不是正式基准，不具备投资解释力；短样本年化指标不得用于参数优化、版本优劣比较或实盘决策。

- Git 提交：`d3c200e1d0052efa422066128d4ad08c80180635`
- 当前分支：`codex/v6-baseline-validation`
- 测试日期：2026-07-31
- 总体结论：现有自动化测试全部通过，但基准验证不通过。代码审计发现成交时间错位、滑点缺失，且现有测试没有覆盖这两项关键规则。

## 实际命令与结果

| 范围 | 命令 | 结果 |
|---|---|---|
| Node | `npm test` | 通过：5/5 |
| Python V6 | `.venv/bin/python -m unittest discover -s tests -v` | 通过：4/4 |
| 旧 Python 框架 | `../etf-rotation-v6/.venv/bin/python -m unittest discover -s test -v` | 通过：1/1 |
| 因子数学 | `.venv/bin/python -m unittest discover -s tests -p 'test_factor_math.py' -v` | 通过：1/1 |
| 无未来函数 | `.venv/bin/python -m unittest discover -s tests -p 'test_no_lookahead.py' -v` | 通过：1/1 |
| 仓位限制 | `.venv/bin/python -m unittest discover -s tests -p 'test_position_limits.py' -v` | 通过：1/1 |
| 调仓 | `.venv/bin/python -m unittest discover -s tests -p 'test_rebalance.py' -v` | 通过：1/1 |
| 可重复性 | 两次运行 `scripts/run_backtest.py --output <临时目录>`，以 `cmp` 比对指标和净值曲线 | 通过：两类输出均逐字节一致 |
| V6.0 基准回测 | `.venv/bin/python scripts/run_backtest.py` | 成功：退出码 0 |

## 覆盖缺口

- 没有独立的“信号日与成交日”测试。现有 `test_rebalance.py` 只检查首日空仓和成本为有限值，不能证明 T 日收盘信号在 T+1 才成交。
- `test_no_lookahead.py` 只验证未来价格变化不影响过去的动量因子，不覆盖完整评分、组合构建、市场状态、风控和成交链路。
- 没有验证手续费数值影响的断言，也没有滑点测试。
- 没有验证 `minimum_history`，该配置当前未被代码使用。
- 没有逐笔成交记录，因此交易次数和平均持仓时间无法测试。

## 失败分类

- 代码错误：成交收益区间与文档规定的 T+1 成交不一致；滑点未实现；`minimum_history` 未生效。
- 测试错误：未发现现有断言本身错误。
- 数据不足：样本仅 20 个交易日、3 个匿名标的，不能验证年度、基准、分市场阶段或真实投资表现。
- 规则待确认：复权方式、数据来源、基准指数、滑点参数、成交价类型、交易次数口径、平均持仓口径。
