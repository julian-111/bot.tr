import time
from typing import Optional, List
import pandas as pd
import pandas_ta as ta
from src.logger import setup_logger


class ScalpingStrategy:
    def __init__(self, streamer, order_manager, symbol: str, risk_usdt: float = 10.0, tp_pct: float = 0.003, sl_pct: float = 0.005, max_open_minutes: int = 20, adx_threshold: float = 25.0, rsi_threshold: float = 68.0, logger=None):
        self.streamer = streamer
        self.md = streamer
        self.om = order_manager
        self.symbol = symbol
        self.risk_usdt = float(risk_usdt)
        self.tp_pct = float(tp_pct)
        self.sl_pct = float(sl_pct)
        self.max_open_secs = int(max_open_minutes) * 60
        self.adx_threshold = float(adx_threshold)
        self.rsi_threshold = float(rsi_threshold)
        self.logger = logger if logger is not None else setup_logger("ScalpingStrategy")
        
        # Calcular y loguear Ratio Riesgo:Beneficio
        rr_ratio = self.tp_pct / self.sl_pct if self.sl_pct > 0 else 0
        self.logger.info(f"🔧 Estrategia Configurada:")
        self.logger.info(f"   • Riesgo (SL): {self.sl_pct*100:.2f}%")
        self.logger.info(f"   • Beneficio (TP): {self.tp_pct*100:.2f}%")
        self.logger.info(f"   • Ratio R:R: 1:{rr_ratio:.1f} (Objetivo: 1:2)")
        self.logger.info(f"   • Filtro ADX: > {self.adx_threshold}")
        self.logger.info(f"   • Filtro RSI: < {self.rsi_threshold}")

        # Obtener y guardar el valor mínimo de la orden
        self._min_order_value = self.om.get_min_order_value()
        if self._min_order_value > 0:
            self.logger.info(f"   • Mínimo de Orden: {self._min_order_value:.2f} USDT")
        else:
            self.logger.warning("   • No se pudo obtener el mínimo de orden. Se usará un valor por defecto.")
        
        self._prices = pd.DataFrame(columns=['open', 'high', 'low', 'close'])
        self._in_trade = False
        self._entry = 0.0
        self._qty = 0.0
        self._opened_at = 0.0
        self._last_fail_time = 0.0

    def _calculate_indicators(self):
        if len(self._prices) < 25: # No calcular si no hay suficientes datos para ADX
            return None
        
        # Usar una copia para evitar SettingWithCopyWarning
        df = self._prices.copy()

        # Calcular EMA
        df.ta.ema(length=9, append=True)
        df.ta.ema(length=21, append=True)

        # Calcular ADX
        df.ta.adx(length=14, append=True)

        # Calcular RSI
        df.ta.rsi(length=14, append=True)

        return df.iloc[-1] # Devolver la última fila con los indicadores más recientes

    def _should_buy(self, indicators) -> (bool, str):
        if indicators is None or self._in_trade:
            return False, ""

        ema9 = indicators.get('EMA_9')
        ema21 = indicators.get('EMA_21')
        adx = indicators.get('ADX_14')
        rsi = indicators.get('RSI_14')

        if ema9 is None or ema21 is None or adx is None or rsi is None:
            return False, ""

        # 1. Condición de Cruce de Medias (Señal de Dirección)
        buy_signal = ema9 > ema21

        # 2. Condición de Fortaleza de Tendencia (Filtro de Ruido)
        is_trending = adx > self.adx_threshold

        # 3. Condición de Momentum (Filtro de Sobrecrompra)
        is_not_overbought = rsi < self.rsi_threshold

        # Lógica de decisión y logging
        if buy_signal and is_trending:
            if is_not_overbought:
                return True, "ok"
            else:
                return False, "rsi_overbought" # Nueva razón de rechazo
        
        if buy_signal and not is_trending:
            return False, "lateral"
        
        return False, ""

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
            # Añadir el nuevo precio al DataFrame
            new_row = pd.DataFrame([{'open': price, 'high': price, 'low': price, 'close': price}])
            self._prices = pd.concat([self._prices, new_row], ignore_index=True)

            # Mantener el DataFrame con un tamaño manejable
            if len(self._prices) > 1000:
                self._prices = self._prices.iloc[-1000:]

            # Calcular indicadores
            indicators = self._calculate_indicators()

            # Decisión de Compra
            should_buy, reason = self._should_buy(indicators)
            if should_buy:
                # Evitar reintentos inmediatos si falló recientemente
                if time.time() - self._last_fail_time < 60:
                    return

                # --- VALIDACIÓN DE MONTO MÍNIMO ---
                if self.risk_usdt < self._min_order_value:
                    self.logger.debug(f"Intento de compra omitido. Riesgo ({self.risk_usdt} USDT) es menor al mínimo requerido ({self._min_order_value} USDT).")
                    return
                # --- FIN DE VALIDACIÓN ---

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
            
            elif reason == "lateral":
                adx_value = indicators.get('ADX_14', 0)
                self.logger.info(f"Mercado lateral detectado (ADX: {adx_value:.2f}). Esperando más volatilidad para operar.")
            
            elif reason == "rsi_overbought":
                rsi_value = indicators.get('RSI_14', 0)
                self.logger.info(f"Compra rechazada por sobrecompra (RSI: {rsi_value:.2f} >= {self.rsi_threshold}). Evitando entrada de alto riesgo.")

            # Decisión de Cierre
            close_reason = self._should_close(float(price))
            if close_reason:
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
                self.logger.info(f"   • Resultado:    {result_text} | PnL: {total_pnl:+.2f} USDT")
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
