"""Portfolio-level drawdown stop with a deterministic cooldown."""

from __future__ import annotations


class DrawdownGuard:
    def __init__(self, max_drawdown: float, cooldown_days: int) -> None:
        self.max_drawdown = max_drawdown
        self.cooldown_days = cooldown_days
        self.peak = 1.0
        self.cooldown_left = 0

    def exposure_multiplier(self, equity: float) -> float:
        if equity <= 0.0:
            raise ValueError("equity must remain positive")
        self.peak = max(self.peak, equity)
        drawdown = equity / self.peak - 1.0
        if drawdown <= -self.max_drawdown and self.cooldown_left == 0:
            self.cooldown_left = self.cooldown_days
        if self.cooldown_left > 0:
            self.cooldown_left -= 1
            # The old high-water mark belongs to the stopped risk episode.
            # Reset it at the end of cooldown so the same loss cannot retrigger
            # indefinitely while the portfolio is in cash.
            if self.cooldown_left == 0:
                self.peak = equity
            return 0.0
        return 1.0
