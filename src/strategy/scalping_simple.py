import time
from typing import Optional, List
from src.logger import setup_logger


class ScalpingStrategy:
    def __init__(self, streamer, order_manager, symbol: str, risk_usdt: float = 10.0, tp_pct: float = 0.003, sl_pct: float = 0.005, max_open_minutes: int = 20, logger=None):
        self.streamer = streamer
        self.md = streamer
        self.om = order_manager
        self.symbol = symbol
        self.risk_usdt = float(risk_usdt)
        self.tp_pct = float(tp_pct)
        self.sl_pct = float(sl_pct)
        self.max_open_secs = int(max_open_minutes) * 60
        self.logger = logger if logger is not None else setup_logger("ScalpingStrategy")
        self._prices: List[float] = []
        self._in_trade = False
        self._entry = 0.0
        self._qty = 0.0
        self._opened_at = 0.0

    def _ema(self, period: int) -> Optional[float]:
        if len(self._prices) < period:
            return None
        k = 2 / (period + 1)
        e = None
        for v in self._prices[-period:]:
            e = v if e is None else v * k + e * (1 - k)
        return e

    def _should_buy(self) -> bool:
        e9 = self._ema(9)
        e21 = self._ema(21)
        if e9 is None or e21 is None:
            return False
        return e9 > e21 and not self._in_trade

    def _should_close(self, price: float) -> Optional[str]:
        if not self._in_trade:
            return None
        if price >= self._entry * (1 + self.tp_pct):
            return "tp"
        if price <= self._entry * (1 - self.sl_pct):
            return "sl"
        if self._opened_at and (time.time() - self._opened_at) > self.max_open_secs:
            return "timeout"
        return None

    def on_tick(self, price: float):
        try:
            self._prices.append(float(price))
            if len(self._prices) > 1000:
                self._prices = self._prices[-1000:]
            if not self._in_trade and self._should_buy():
                order = self.om.market_buy_usdt(self.risk_usdt)
                fill = self.om.last_fill(order_response=order) or {}
                qty = float(fill.get("execQty") or 0)
                lp = float(fill.get("execPrice") or price)
                if qty <= 0:
                    return
                self._qty = qty
                self._entry = lp
                self._opened_at = time.time()
                self._in_trade = True
                return
            reason = self._should_close(float(price))
            if reason:
                qty_str = f"{self._qty:.6f}"
                self.om.market_sell(qty_str)
                self._in_trade = False
                self._qty = 0.0
                self._entry = 0.0
                self._opened_at = 0.0
        except Exception as e:
            if self.logger:
                self.logger.error(f"on_tick error: {e}")

    def run(self):
        self.md.start(on_tick=self.on_tick)
        if self.logger:
            self.logger.info("ScalpingStrategy running...")
        try:
            while True:
                time.sleep(0.5)
        finally:
            self.md.stop()
