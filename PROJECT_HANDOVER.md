# ETF 量化轮动系统（V6.x）项目交接文档

> 更新时间：2026-08-01
> 当前状态：持续开发中
> 当前主分支：`main`
> 当前功能分支：`codex/add-real-etf-data`

## 一、项目目标

本项目用于构建一个可长期维护、可验证、接近实盘的 ETF 量化轮动系统。目标不是追求
历史收益最大，而是保证回测逻辑正确、消除未来函数和成交时间错误、建立真实交易成本
模型与完整测试体系，并在后续接入真实 ETF 历史数据。

计划路径：

```text
ETF轮动V6
→ 工程验证
→ 真实历史验证
→ 样本外验证
→ V6.1策略优化
→ 模拟盘
→ 实盘
```

在用户明确授权前，禁止连接券商、运行模拟盘或执行实盘交易。

## 二、Git 开发规范

采用以下流程：

```text
main
→ 一个功能对应一个独立分支
→ 测试
→ Pull Request
→ Review
→ Merge
→ 删除已合并分支
```

禁止直接在 `main` 开发或直接推送功能提交。

### 已完成并合并

#### `codex/strategy-bootstrap`

- 建立 `AGENTS.md`、仓库审计、开发流程和未决事项文档。
- 已通过 Pull Request 合并。

#### `codex/v6-baseline-validation`

- 建立 V6 阻断验证记录。
- 结论：`C. 暂不冻结`。
- 当时的阻断项包括成交时序错误、滑点未实现和 sample 数据不足。
- 已通过 Pull Request 合并。

#### `codex/fix-t1-execution`

- 修复 T 日收盘信号错误参与 T→T+1 收益的问题。
- 当前模型：T 日收盘产生信号，T+1 收盘成交，新权重影响 T+1→T+2 收益。
- 同时修复权重自然漂移、免费每日再平衡、真实 turnover、现金保留和成交事件过滤。
- 已通过 Pull Request 合并。

#### `codex/add-slippage-and-ledger`

- 新增滑点模型、成交台账 `trade_log.csv`、分项成本和成交统计。
- 当前提交：`adee6ca feat(backtest): add slippage model and trade ledger`。
- 本地与远程功能分支已同步。
- 测试全部通过。
- 已通过 Pull Request #4 合并。

### 当前开发

#### `codex/enforce-minimum-history`

- 每只 ETF 独立累计历史观察数。
- 历史不足或关键因子尚未形成的 ETF 不参与当日评分与组合选择。
- 不使用未来数据补足过去资格。
- 已通过 Pull Request #5 合并。

#### `codex/add-real-etf-data`

- 建立 AkShare/东方财富 ETF 日线获取、标准化、质量校验和清单哈希。
- 当前研究池覆盖宽基、科创、红利、黄金和国债六类ETF。
- 真实数据已完成端到端回测入口验证，原始行情不提交Git。
- 当前状态：实现与测试已完成，等待提交和 Pull Request。

### 分支清理状态

截至本文更新时，已合并功能分支的本地和远程引用仍可见。是否由仓库维护者在合并后
删除，待执行；本文不把“PR 已合并”等同于“分支已删除”。

## 三、当前回测能力

已经实现：

- T+1 收盘成交
- 持仓权重自然漂移
- 基于成交前实际权重的 turnover
- 未投资现金保留
- commission
- slippage
- `trade_log`
- 买卖次数、平均每笔换手和累计成本统计
- 已完整平仓持仓周期的平均持仓时间
- 相同数据与配置下的可重复性验证

尚未实现或尚未完成：

- `minimum_history` 已按每只标的自身历史执行
- 历史时点完整ETF池及退市、合并、更名数据
- 沪深300 Benchmark、超额收益、跟踪误差和信息比率
- 样本外、Walk Forward / Rolling 和牛熊震荡分段框架（当前被回撤重复触发问题阻断）
- 停牌、退市、历史 ETF 池和幸存者偏差规则
- 滑点参数的真实市场校准

## 四、当前策略与仓库结构

仓库包含三套用途不同的实现，不得默认等价：

1. 根目录 JavaScript：实时 ETF 雷达和组合建议。
2. `etf-rotation-v6`：当前 Python V6 研究回测实现。
3. `ETF-Quant-System`：历史研究框架。

Python V6 当前已确认的主要组成包括：

- 多周期动量
- 路径效率
- 低波动
- 低回撤
- 市场状态与风险暴露
- 组合选择和仓位限制
- 调仓、回撤风控及回测

MACD 未在当前 Python V6 因子实现中确认，不得写成已实现事实。JavaScript 与 Python
的因子公式、窗口和组合逻辑仍不一致，详见 `docs/repo_audit.md` 和
`docs/unknowns.md`。

当前禁止修改：

- 因子公式和因子权重
- 牛熊/市场状态判断
- 仓位比例
- 调仓周期
- `strategy_v6.yaml` 中已经确认的策略参数

在明确任务范围内可修改：

- 回测引擎
- 交易成本
- 测试
- 文档
- 统计

## 五、已修复的重要问题

### P0：成交时间

修复前：T 日信号错误参与 T→T+1 收益。
修复后：T 日收盘产生信号，T+1 收盘成交，新权重从 T+1→T+2 生效。

### P1：权重漂移

修复前：非调仓日恢复 `target_weight`，等同于免费每日再平衡。
修复后：收益发生后权重自然漂移；成交前实际权重用于 turnover 和后续成交。

### P1：成交事件

只有满足以下条件的资产才记录实际成交：

```text
abs(target_weight - previous_weight) > epsilon
```

零变化和 0→0 不记录成交。

### P1：交易成本

手续费与滑点分别计算、分别记录，并在成交日合计扣除一次。台账汇总与净值曲线逐日
成本已经过一致性验证。

## 六、当前测试状态

最近一次完整验收结果：

| 测试组 | 结果 |
|---|---:|
| Node | 5/5 通过 |
| Python V6 全部测试 | 33/33 通过 |
| 旧 Python 框架 | 1/1 通过 |
| 滑点与成交台账定向测试 | 6/6 通过 |
| T+1 成交与权重漂移定向测试 | 13/13 通过 |
| 可重复性 | 指标、净值曲线和成交台账逐字节一致 |
| `git diff --check` | 通过 |

真实运行命令：

```text
# 仓库根目录
npm test

# etf-rotation-v6/
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/run_backtest.py --output <临时目录>

# ETF-Quant-System/
../etf-rotation-v6/.venv/bin/python -m unittest discover -s test -v
```

验证回测应优先写入临时目录，避免覆盖受版本控制的历史基准文件。

## 七、当前成交台账

`trade_log.csv` 字段：

```text
signal_date
execution_date
asset
side
previous_weight
target_weight
turnover
commission
slippage
total_cost
execution_price_type
```

当前 `execution_price_type` 固定为 `close`。`previous_weight` 是成交前经过价格变化后的
实际漂移权重，只记录实际发生权重变化的资产。

平均持仓时间当前只统计已经完整平仓的持仓周期；回测结束时仍未平仓的仓位不进入
均值，部分加减仓不会重置持仓周期。它不是完整的成交批次匹配统计。

## 八、当前成本模型

```text
commission = asset_turnover × transaction_cost
slippage = asset_turnover × slippage_bps / 10000
total_cost = commission + slippage
```

当前配置：

```yaml
risk:
  transaction_cost: 0.0005
  slippage_bps: 5
```

`5 bps = 5 / 10000 = 0.0005`。

在当前归一化组合模型中，滑点按成交金额扣除；其经济含义等价于：

- 买入：成交价格 × `(1 + slippage)`
- 卖出：成交价格 × `(1 - slippage)`

当前只有收盘成交模型。真实买卖价差、最低佣金、申赎费和市场冲击仍为“待确认”。

## 九、安全边界

禁止：

- 未来函数和数据泄漏
- T 日信号参与 T→T+1 收益
- 免费每日再平衡
- 未经授权修改因子、权重、市场状态、仓位或调仓频率
- 自动连接券商、模拟盘或实盘下单
- 提交 `.env`、API Key、Token、SSH Key、券商账号、密码、真实持仓或私人交易数据

根目录 `data/` 按本地敏感运行数据处理，不读取具体持仓、不提交、不移动、不删除。

## 十、下一阶段路线

### Phase 4：`minimum_history`（当前已实现，等待PR）

已实现 `minimum_history`：上市历史不足或关键因子未形成的 ETF 不得参与排名；规则按
每只 ETF 独立计算，且不会因未来新增数据改变过去资格。不得通过修改因子或提高样本
收益绕过暖机规则。

### Phase 5：真实 ETF 历史数据（已完成）

已接入 AkShare/东方财富前复权日线，覆盖股票宽基、科创、红利、黄金和国债等类别，
并保存获取清单、实际区间、每标的行数和文件哈希。停牌、退市和历史完整ETF池仍需
专门数据支持，不能把当前固定研究池描述为无幸存者偏差。

### Phase 6：Benchmark（已完成）

正式基准为沪深300指数，按共同交易日计算基准收益、超额收益、跟踪误差和信息比率；
基准不参与策略信号。验证记录见 `etf-rotation-v6/docs/benchmark_validation.md`。

### Phase 7：样本外验证（框架完成，结果受阻）

已实施固定参数 Walk Forward、Rolling 以及牛市、熊市、震荡市分阶段验证。验证发现
`DrawdownGuard` 冷却后立即重复触发并永久清仓，须先修复再复验。记录见
`etf-rotation-v6/docs/out_of_sample_validation.md`。

### Phase 8：V6.1

策略优化必须一次只修改一个因素，重点可包括降低回撤、降低换手或提高样本外
Sharpe。不得同时改动多个因素，也不得只按总收益判断改善。

## 十一、新 Agent 启动顺序

任何新 Agent 进入本项目时必须：

1. 读取个人协作档案 `/Users/xy./Documents/a股/.agent/CODEX_WORKING_PROFILE.md`。
2. 读取根目录 `AGENTS.md`。
3. 读取根目录 `PROJECT_HANDOVER.md`。
4. 执行 `git status --short` 和 `git branch --show-current`。
5. 确认项目目录、当前分支和工作区状态。
6. 只在独立功能分支开始开发。

若工作区不干净，必须先报告并保护已有修改，不得擅自 reset、clean、stash、删除或
覆盖。

## 十二、当前总体判断

- 工程成熟度：较高，但数据层和完整交易规则仍未完成。
- 回测可信度：成交时序、漂移、成本和事件链路已经有测试；真实数据有效性仍不足。
- 策略可信度：当前仅使用 sample 数据，不能评价真实投资效果。
- 当前主要矛盾：工程回测能力已经明显完善，但真实历史数据、ETF 历史池和样本外验证
  尚未建立。
- 下一阶段重点：合并 `minimum_history` 后完成数据规范并接入真实 ETF 历史数据；不要
  继续增加策略复杂度。

> 当前所有 sample 回测结果均属于工程验证，不代表真实投资效果，也不得用于实盘决策。
