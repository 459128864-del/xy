# MacBook ETF Rotation V6 Integrity Report

Validation date: 2026-08-15 (Asia/Shanghai)

## 1. Project

- Project path: `/Users/xiayong/Documents/GitHub/xy/etf-rotation-v6`
- Validation worktree: `/Users/xiayong/Documents/ChatGPT/etf 轮动v6/xy-etf-validation/etf-rotation-v6`
- Repository: `https://github.com/459128864-del/xy.git`
- Branch: `codex/etf-v6-macbook-validation-fixes`
- Base commit: `59a1eaf827862ba9b57b6baa44ef7f0de2930be8` (`origin/main`)
- Project structure: PASS

## 2. Authoritative Strategy

The authoritative V6 strategy is the implementation on `main` under
`etf-rotation-v6/`, together with its `README.md`, `docs/strategy_v6.md`, and
formal configuration files.

The formal model contains:

- multi-period momentum;
- path efficiency;
- low volatility;
- low drawdown;
- market trend and breadth;
- attack, balanced, and defense regimes with exposure control.

The earlier integrity report incorrectly treated MA60/MA120, M20/M60, and MACD
DIF/DEA concepts from an early design discussion as mandatory V6 acceptance
criteria. They are not part of the authoritative current strategy. The earlier
`C — PARTIALLY MIGRATED` result is therefore superseded.

No MA60/M20/MACD factor was restored or added. Formal strategy parameters,
factor formulas, factor weights, position sizing, rebalance frequency,
`minimum_history`, ranking, drawdown rules, and T+1 semantics are unchanged from
`origin/main`.

## 3. Git Isolation

- The source worktree remains on `codex/github-mention-featintraday-t-tt/t` and
  retains all pre-existing `intraday-t` modifications and untracked files.
- The current branch was created directly from `origin/main`; the unrelated
  branch and its commit were not merged or cherry-picked.
- Unrelated files included in this branch: none.
- `requirements.txt` was not changed because its dependency declarations were
  already correct. The MacBook issue was an unpopulated virtual environment,
  repaired by installing the declared requirements plus `packaging`.

## 4. Validation Fixes

1. `src/backtest.py`: calculate the current order's weight changes before
   validating execution-price availability. Previously the validation could
   inspect the prior loop's value.
2. `tests/test_signal_date_execution_date_no_same_close_execution.py`: add a
   regression test proving a first T+1 execution with no raw close fails fast.
3. This report.

## 5. Execution and Data

- T+1 execution: PASS
- Slippage 5 bps: PASS
- Trade Ledger: PASS
- ETF Universe Provider: PASS
- Current configured price provider: AkShare
- Point-in-time universe implementations and provider-boundary tests: PASS

## 6. Environment

- Python: 3.14.6
- Virtualenv: `/Users/xiayong/Documents/GitHub/xy/.venv`
- Dependencies: PASS; `pip check` returned `No broken requirements found`.

## 7. Tests and Backtest

- Official unittest gate: PASS, 82/82 tests.
- New regression test: PASS.
- Smoke backtest: PASS using bundled sample data and formal V6 configuration.
- Smoke output: `/tmp/etf-v6-macbook-final-smoke`
- Trades: 2 buys, 0 sells.
- Cumulative commission: 0.0005.
- Cumulative slippage: 0.0005.
- Cumulative cost: 0.001.
- `git diff --check`: PASS.
- Strategy drift check against `origin/main`: PASS; no differences in formal
  configuration, factor, scoring, regime, portfolio, risk-control, or strategy
  documentation files.

## 8. Final Status

```text
MACBOOK ETF V6 STATUS:

A — COMPLETE & UP TO DATE
```

ETF Rotation V6 is completely migrated to this MacBook. The dedicated branch is
based on the latest `origin/main` and contains only isolated validation fixes,
their regression coverage, and this report.
