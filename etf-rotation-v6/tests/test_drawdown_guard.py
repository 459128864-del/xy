import unittest

from src.risk_control import DrawdownGuard


class DrawdownGuardTest(unittest.TestCase):
    def test_reenters_after_exact_cooldown_instead_of_retriggering(self) -> None:
        guard = DrawdownGuard(max_drawdown=0.08, cooldown_days=3)
        self.assertEqual(guard.exposure_multiplier(1.0), 1.0)
        self.assertEqual(guard.exposure_multiplier(0.91), 0.0)
        self.assertEqual(guard.exposure_multiplier(0.91), 0.0)
        self.assertEqual(guard.exposure_multiplier(0.91), 0.0)
        self.assertEqual(guard.exposure_multiplier(0.91), 1.0)

    def test_new_drawdown_after_reentry_can_trigger_new_episode(self) -> None:
        guard = DrawdownGuard(max_drawdown=0.08, cooldown_days=1)
        self.assertEqual(guard.exposure_multiplier(1.0), 1.0)
        self.assertEqual(guard.exposure_multiplier(0.90), 0.0)
        self.assertEqual(guard.exposure_multiplier(0.90), 1.0)
        self.assertEqual(guard.exposure_multiplier(0.82), 0.0)

    def test_peak_can_advance_after_reentry(self) -> None:
        guard = DrawdownGuard(max_drawdown=0.08, cooldown_days=1)
        guard.exposure_multiplier(1.0)
        guard.exposure_multiplier(0.90)
        self.assertEqual(guard.exposure_multiplier(0.95), 1.0)
        self.assertEqual(guard.peak, 0.95)

    def test_nonpositive_equity_is_rejected(self) -> None:
        guard = DrawdownGuard(max_drawdown=0.08, cooldown_days=1)
        with self.assertRaisesRegex(ValueError, "positive"):
            guard.exposure_multiplier(0.0)


if __name__ == "__main__":
    unittest.main()
