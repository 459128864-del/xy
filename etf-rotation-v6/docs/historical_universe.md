# 历史 ETF 池与幸存者偏差门禁

## 结论

当前仓库自带的六只 ETF 是固定研究池，不能据此宣称已控制幸存者偏差。
免费 BaoStock 基础目录在 2026-08-01 的实测结果仅包含存续 ETF（ETF 1,616
只、退市 0 只，已知退市代码 510220 不在结果中），因此不得把它作为完整历史池。

系统现已支持导入包含上市和退市产品的权威历史目录，但仓库不附带需授权的目录或
完整原始行情。没有合格目录时，manifest 必须保持：

- `historical_universe_complete: false`
- `survivorship_bias_controlled: false`

## 目录契约

CSV 必须包含：

- `symbol`：交易代码；
- `name`：当时产品名称；
- `listing_date`：上市日期；
- `delisting_date`：终止上市生效日期，仍存续时留空；候选资格采用右开区间
  `listing_date <= date < delisting_date`；
- `source`：逐行数据来源。

配套 JSON 元数据必须包含：

- `provider_id`、`source_name`、`source_url`；
- `authoritative: true`；
- `scope: all_sh_sz_etfs`；
- `complete_through`：目录完整覆盖日期，不得早于回测结束日。
- `expected_symbol_count`：供应商该版本声明的总标的数，必须与文件唯一代码数一致。

示例命令：

```bash
cd etf-rotation-v6
.venv/bin/python scripts/fetch_real_data.py \
  --historical-universe-catalog /受控目录/etf_catalog.csv \
  --catalog-metadata /受控目录/etf_catalog.metadata.json
```

真实目录和完整行情必须保存在 Git 忽略的受控位置，不得提交私人或授权受限数据。

## 强制校验

数据管线执行以下门禁：

1. 上市、退市日期合法且代码唯一；
2. 每个日期的候选池只包含当日已经上市且尚未退市的产品；
3. 与回测区间有生命周期交集的每只 ETF 都必须有行情；
4. 行情不得出现在上市前或退市后；
5. manifest 记录目录哈希、来源元数据和覆盖统计；
6. 自称全生命周期的目录必须实际包含退市 ETF；
7. 仅修改两个布尔字段不能通过研究结论门禁。

满足门禁只证明历史池与行情覆盖的工程条件成立，不代表策略有效，也不替代复权、
停牌、清盘价值和样本外验证。

## 聚宽目录适配器

项目批准的首个全生命周期目录供应商适配器是 JoinQuant JQData。它是第三方数据服务，
不是交易所官方原始档案；项目依据其公开接口契约和退市哨兵校验接入。官方文档说明
`get_all_securities(types=['fund'], date=None)` 返回上市日期、退市日期和基金细分类型；
传入具体日期只会返回该日仍上市证券，因此适配器固定使用 `date=None`。

凭据只从环境变量读取：

```bash
export JQDATA_USERNAME="你的聚宽账号"
export JQDATA_PASSWORD="你的聚宽密码"
cd etf-rotation-v6
.venv/bin/python scripts/fetch_joinquant_universe.py
```

脚本不会输出账号或密码。默认结果写入 Git 忽略的 `data/real/`。输出必须包含已知退市
ETF `510220`，否则立即拒绝该响应，防止误把当前存续名单当成全历史目录。
