# 同花顺 iFinD HTTP 行情接口

## 当前实现范围

当前数据层已实现官方 iFinD HTTP API 的价格传输适配，但不会在导入模块或创建 Provider
时自动发起网络请求。只有显式调用历史或实时行情方法时才会连接服务端。

已实现：

- 历史日线：`POST https://quantapi.51ifind.com/api/v1/cmd_history_quotation`；
- 实时行情：`POST https://quantapi.51ifind.com/api/v1/real_time_quotation`；
- 获取当前有效 access token：
  `POST https://quantapi.51ifind.com/api/v1/get_access_token`；
- 上海、深圳 ETF 代码与同花顺代码的显式转换；
- OHLC、成交量、成交额、复权方式和复权因子的标准字段映射；
- 按标的数、指标数和日期自动切分历史请求，默认将每次请求控制在45,000个理论
  单元格以内；
- access token 失效后最多一次的安全重试；
- 固定研究池数据进入现有 `data_pipeline` 的命令行入口。

未实现：

- 自动调用 `update_access_token`。该接口会使旧 access token 失效，因此禁止自动调用；
- 全量历史 ETF 目录下载。同花顺 HTTP 手册没有给出可直接复用的 ETF 全历史目录指标
  协议，必须由已授权的超级命令生成并另行评审；
- 自动扩展为全市场候选池；
- 券商连接、模拟盘或实盘交易。

## 安全认证

凭据只从进程环境读取。真实值不得写入 `.env.example`、源代码、测试、日志或 Git。

```bash
export THS_ACCESS_TOKEN="本地有效access token"
export THS_REFRESH_TOKEN="本地refresh token"
```

两者至少配置一个：

- 若存在 `THS_ACCESS_TOKEN`，直接用于数据请求；
- 若 access token 缺失，使用 `THS_REFRESH_TOKEN` 获取当前有效 token；
- 若服务端明确返回 access token 失效码，且配置了 refresh token，则清除内存缓存并
  获取当前有效 token，最多重试一次；
- token 只保存在进程内存中，不写入文件和 manifest；
- 错误信息不回显服务端响应正文，避免意外泄露敏感内容。

官方手册说明 refresh token 有效期与账号到期日一致，access token 初次生成后七天失效；
更新 refresh token 会使过去的 refresh token 和 access token 全部失效。

`THS_APP_KEY` 和 `THS_APP_SECRET` 只作为已有部署的兼容环境字段保留。当前官方 HTTP
行情协议不发送这两个字段。

## 历史行情口径

历史请求固定使用：

```text
Interval=D
Fill=Blank
Currency=RMB
CPS=1/2/3
```

其中：

- `CPS=1`：不复权；
- `CPS=2`：前复权（分红再投），映射项目 `qfq`；
- `CPS=3`：后复权（分红再投），映射项目 `hfq`；
- `Fill=Blank`：不沿用上一日行情，不把停牌或缺失行情伪装成正常成交数据。

请求指标：

```text
open,high,low,close,volume,amount,ths_af_stock
```

同花顺账号的数据量和单次请求限制可能不同。传输层按“所有日历日都有数据”的最保守
假设分块，不使用未来交易日历估算，也不让相邻日期块重叠。默认45,000个理论单元格
低于官方免费权限说明中的50,000单元格单次历史行情限制。

标准化字段：

| iFinD字段 | 项目字段 |
|---|---|
| `time` | `date` |
| `thscode` | `symbol` |
| `open/high/low/close` | `open/high/low/close` |
| `volume` | `volume` |
| `amount` | `amount` |
| `ths_af_stock` | `adjust_factor` |
| 请求的CPS口径 | `adjustment` |

## 实时行情口径

实时接口当前映射：

| iFinD字段 | 项目字段 |
|---|---|
| `tradeDate + tradeTime` | `timestamp` |
| `thscode` | `symbol` |
| `latest` | `last` |
| `preClose` | `previous_close` |
| `open/high/low` | `open/high/low` |
| `latestVolume` | `volume`（最新一笔成交量） |
| `latestAmount` | `amount`（最新一笔成交额） |

实时接口目前仅作为行情能力预留，不连接回测，不触发交易。

## 本地运行

设置本地环境变量后，在 `etf-rotation-v6` 目录运行：

```bash
.venv/bin/python scripts/fetch_ths_real_data.py
```

可使用临时输出避免覆盖已有本地数据：

```bash
.venv/bin/python scripts/fetch_ths_real_data.py \
  --output /tmp/ths_etf_daily.csv \
  --manifest /tmp/ths_manifest.json
```

该入口当前只接受 `fixed_research_universe`。若配置为全市场点时池会立即报错，不会
静默退回固定池，也不会伪称已经控制幸存者偏差。

## 测试边界

自动测试全部使用内存 Fake HTTP Client，验证请求 URL、请求头、请求体、字段映射、
token 获取、单次重试、错误脱敏、固定池管线接入和全市场模式门禁。自动测试不读取
本机环境变量，不调用真实 API，也不消耗数据额度。
