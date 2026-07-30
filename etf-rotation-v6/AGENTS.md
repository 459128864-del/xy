# Repository guidance

- Use Python 3.10+ and keep strategy logic deterministic.
- Never use future observations when forming a signal. Positions decided on day
  `t` may earn returns only from `t` to `t+1`.
- Put tunable strategy parameters in `config/strategy_v6.yaml`.
- Preserve the input contract documented in `docs/data_dictionary.md`.
- Run `python -m unittest discover -s tests` before handing off changes.
- Treat all performance output as research evidence, not an investment promise.
