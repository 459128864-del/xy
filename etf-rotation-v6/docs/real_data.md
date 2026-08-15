# 真实 ETF 历史数据

## 数据源与口径

- 数据接口：AkShare `fund_etf_hist_em`，底层来源为东方财富 ETF 日行情。
- 频率：日线。
- 复权：前复权 `qfq`。
- 请求区间：见 `config/data_sources.yaml`。
- 本地输出：`data/real/etf_daily.csv` 与 `data/real/manifest.json`。
- 原始行情目录已被 Git 忽略，不得提交完整行情数据。

AkShare 官方文档说明该接口按日频返回指定 ETF、指定区间的历史行情，并支持不复权、
前复权和后复权。当前工程选择前复权以保持用于因子与收益计算的价格序列连续；该选择
不得与其他复权口径混用。

## 当前标的池

| 代码 | 名称 | 类别 |
|---|---|---|
| 510300 | 沪深300ETF | 大盘宽基 |
| 510500 | 中证500ETF | 中盘宽基 |
| 588000 | 科创50ETF | 科创宽基 |
| 510880 | 红利ETF | 红利风格 |
| 518880 | 黄金ETF | 黄金 |
| 511010 | 国债ETF | 国债 |

该池是当前工程研究池，不代表历史任意时点的完整可投资 ETF 池。历史目录的工程规则
已明确，完整授权数据源仍为“待确认”。

## 获取命令

在 `etf-rotation-v6` 目录运行：

```bash
.venv/bin/python scripts/fetch_real_data.py
```

验证时可用 `--output` 和 `--manifest` 写入临时目录，避免污染项目数据目录。

东方财富端点不可用时，可在已设置 JQData 环境变量的终端运行：

```bash
.venv/bin/python scripts/fetch_joinquant_real_data.py
```

JQData 入口保持当前固定六只研究池，使用前复权日线并跳过供应商的停牌前值填充。

已获得 iFinD HTTP 权限时，也可在本地设置 `THS_ACCESS_TOKEN` 或
`THS_REFRESH_TOKEN` 后运行：

```bash
.venv/bin/python scripts/fetch_ths_real_data.py
```

该入口通过官方 `cmd_history_quotation` 获取日线，使用 `Fill=Blank`，并按供应商单次
数据量限制自动分块。当前同样只允许固定研究池；同花顺全量历史ETF目录所需的超级
命令协议尚未确认，不得用该入口声称已控制幸存者偏差。详细口径见
`docs/ths_http_provider.md`。

## 质量门禁

- 必须包含 `date`、`symbol`、`close`。
- `date-symbol` 必须唯一。
- 收盘价必须为正。
- 必填字段不得缺失。
- 每只 ETF 保留真实首个可用日期，不生成上市前记录。
- 不对缺失交易日做静默前向填充。
- 清单记录请求区间、实际区间、每标的行数和文件 SHA-256。

真实数据接入只改善数据基础，不证明策略有效。必须完成 Benchmark、样本外和分阶段验证
后，才能评价研究表现。

## 历史ETF池与幸存者偏差门禁

当前下载配置明确写入 `fixed_research_universe`、`historical_universe_complete: false` 和
`survivorship_bias_controlled: false`。清单校验器会拒绝把该数据描述为“已控制幸存者
偏差”。上交所当前ETF列表不等于历史成员池；终止上市ETF只能从交易所公告等历史资料
补录。只有同时纳入沪深交易所历史上市、终止上市、合并和更名记录，并校验对应存续期
行情后，系统才会在 manifest 中生成两个 `true`；配置文件不能直接绕过门禁。详细契约
见 `docs/historical_universe.md`。

全量历史目录不会自动消除固定六只研究池的事后选择偏差。固定池 manifest 只记录
`fixed_universe_lifecycle_only`，两个幸存者偏差结论字段继续为 `false`。全市场点时池是
明确的另一种研究模式，不得与当前 V6 基准混称。

可核验的官方资料入口包括：

- 上交所ETF列表：https://www.sse.com.cn/assortment/fund/etf/list/
- 上交所基金公告：https://etf.sse.com.cn/disclosure/ssenotice/
- 深交所基金业务信息：https://fund.szse.cn/

这项门禁解决“误把固定存活池当无偏历史池”的工程问题，但不会伪造当前公开接口没有
提供的完整退市目录；在完整目录接入前，所有绩效仍必须标注固定研究池限制。

## 基准数据

正式比较基准为沪深300指数（`csi000300`），通过 AkShare 的
`stock_zh_index_daily` 获取。基准仅在回测结束后按共同交易日对齐，不参与因子、
市场状态或交易信号。缺少共同日期时必须报错，不做向前填充。
