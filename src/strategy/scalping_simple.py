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
        
        # Calcular y loguear Ratio Riesgo:Beneficio
        rr_ratio = self.tp_pct / self.sl_pct if self.sl_pct > 0 else 0
        self.logger.info(f"🔧 Estrategia Configurada:")
        self.logger.info(f"   • Riesgo (SL): {self.sl_pct*100:.2f}%")
        self.logger.info(f"   • Beneficio (TP): {self.tp_pct*100:.2f}%")
        self.logger.info(f"   • Ratio R:R: 1:{rr_ratio:.1f} (Objetivo: 1:2)")
        
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
                # Evitar reintentos inmediatos si falló recientemente
                if time.time() - self._last_fail_time < 60:
                    return

                order = self.om.market_buy_usdt(self.risk_usdt)
                
                # Verificar error en la orden inmediatamente
                if order.get('retCode') != 0:
                    self.logger.error(f"❌ Error al enviar orden: {order}")
                    self.logger.warning("Pausando 60s por error de API.")
                    self._last_fail_time = time.time()
                    return

                fill = self.om.last_fill(order_response=order) or {}
                qty = float(fill.get("execQty") or 0)
                lp = float(fill.get("execPrice") or price)
                
                if qty <= 0:
                    self.logger.warning("⚠️ Compra fallida (posible saldo insuficiente). Pausando intentos por 60s.")
                    self._last_fail_time = time.time()
                    return

                self._qty = qty
                self._entry = lp
                self._opened_at = time.time()
                self._in_trade = True
                
                self.logger.info("==========================================")
                self.logger.info(f"🚀 COMPRA EJECUTADA")
                self.logger.info(f"   • Precio:   ${lp:,.2f}")
                self.logger.info(f"   • Cantidad: {qty}")
                self.logger.info(f"   • Total:    ${(lp * qty):,.2f}")
                self.logger.info("==========================================")
                return

            reason = self._should_close(float(price))
            if reason:
                qty_str = f"{self._qty:.6f}"
                self.om.market_sell(qty_str)
                
                # Calcular PnL estimado
                pnl_per_unit = float(price) - self._entry
                total_pnl = pnl_per_unit * self._qty
                result_text = "GANANCIA 🎉" if total_pnl > 0 else "PÉRDIDA ⚠️"
                
                self.logger.info("==========================================")
                self.logger.info(f"💰 VENTA EJECUTADA ({reason.upper()})")
                self.logger.info(f"   • Precio Venta: ${float(price):,.2f}")
                self.logger.info(f"   • Precio Entr.: ${self._entry:,.2f}")
                self.logger.info(f"   • Resultado:    {result_text} ${total_pnl:,.2f}")
                self.logger.info("==========================================")

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
