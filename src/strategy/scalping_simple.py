import time
from typing import Optional, Dict
import pandas as pd
import pandas_ta as ta
from src.logger import setup_logger

class ScalpingStrategy:
    def __init__(self, streamer, order_manager, symbol: str, 
                 risk_usdt: float = 5.0, 
                 tp_pct: float = 0.003, 
                 sl_pct: float = 0.005, # Mantenido por compatibilidad, pero no usado para SL
                 max_open_minutes: int = 20, 
                 adx_threshold: float = 25.0, 
                 rsi_threshold: float = 68.0,
                 atr_multiplier: float = 1.5,
                 volume_multiplier: float = 1.2,
                 logger=None, trade_logger=None):
        
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
        self.atr_multiplier = float(atr_multiplier)
        self.volume_multiplier = float(volume_multiplier)
        self.logger = logger if logger is not None else setup_logger("ScalpingStrategy")
        self.trade_logger = trade_logger
        
        self.logger.info("🔧 Estrategia Avanzada Configurada:")
        self.logger.info(f"   • Riesgo por Trade: {self.risk_usdt} USDT")
        self.logger.info(f"   • Beneficio (TP): {self.tp_pct*100:.2f}%")
        self.logger.info(f"   • SL Dinámico: ATR x {self.atr_multiplier}")
        self.logger.info(f"   • Filtro ADX: > {self.adx_threshold}")
        self.logger.info(f"   • Filtro RSI: < {self.rsi_threshold}")
        self.logger.info(f"   • Filtro Volumen: > Media x {self.volume_multiplier}")

        self._min_order_value = self.om.get_min_order_value()
        if self._min_order_value > 0:
            self.logger.info(f"   • Mínimo de Orden: {self._min_order_value:.2f} USDT")
        
        self._prices = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        self._in_trade = False
        self._entry = 0.0
        self._qty = 0.0
        self._opened_at = 0.0
        self._last_fail_time = 0.0
        self._stop_loss_price = 0.0
        self._trade_closed = False

    def _calculate_indicators(self, df):
        if len(df) < 25:
            return None
        
        df_copy = df.copy()
        df_copy.set_index(pd.to_datetime(df_copy['timestamp'], unit='ms'), inplace=True)
        
        df_copy.ta.ema(length=9, append=True)
        df_copy.ta.ema(length=21, append=True)
        df_copy.ta.adx(length=14, append=True)
        df_copy.ta.rsi(length=14, append=True)
        df_copy.ta.atr(length=14, append=True)
        df_copy['volume_sma'] = df_copy['volume'].rolling(window=20).mean()
        
        return df_copy.iloc[-1]

    def _should_buy(self, indicators) -> (bool, str):
        if indicators is None or self._in_trade:
            return False, ""

        ema9, ema21 = indicators.get('EMA_9'), indicators.get('EMA_21')
        adx, rsi = indicators.get('ADX_14'), indicators.get('RSI_14')
        volume, volume_sma = indicators.get('volume'), indicators.get('volume_sma')

        if any(v is None for v in [ema9, ema21, adx, rsi, volume, volume_sma]):
            return False, ""

        buy_signal = ema9 > ema21
        is_trending = adx > self.adx_threshold
        is_not_overbought = rsi < self.rsi_threshold
        has_volume = volume > (volume_sma * self.volume_multiplier)

        if buy_signal and is_trending and is_not_overbought:
            if has_volume:
                return True, "ok"
            else:
                return False, "low_volume"
        
        if buy_signal and is_trending and not is_not_overbought: return False, "rsi_overbought"
        if buy_signal and not is_trending: return False, "lateral"
        return False, ""

    def _should_close(self, price: float) -> Optional[str]:
        if not self._in_trade: return None
        if price >= self._entry * (1 + self.tp_pct): return "tp"
        if price <= self._stop_loss_price: return "sl"
        if self._opened_at and (time.time() - self._opened_at) > self.max_open_secs: return "timeout"
        return None

    def on_kline(self, kline: Dict):
        try:
            price = kline['close']
            new_row = pd.DataFrame([kline])
            self._prices = pd.concat([self._prices, new_row], ignore_index=True)

            if len(self._prices) > 1000:
                self._prices = self._prices.iloc[-1000:]

            indicators = self._calculate_indicators(self._prices)

            should_buy, reason = self._should_buy(indicators)
            if should_buy:
                if time.time() - self._last_fail_time < 60: return

                if self.risk_usdt < self._min_order_value:
                    self.logger.debug(f"Compra omitida. Riesgo ({self.risk_usdt} USDT) < Mínimo ({self._min_order_value} USDT).")
                    return

                order = self.om.market_buy_usdt(self.risk_usdt)
                
                if order.get('retCode') != 0:
                    self.logger.error(f"❌ Error al enviar orden: {order}")
                    self._last_fail_time = time.time()
                    return

                fill = self.om.last_fill(order_response=order) or {}
                qty, lp = float(fill.get("execQty", 0)), float(fill.get("execPrice", price))
                
                if qty <= 0:
                    self.logger.warning("⚠️ Compra fallida (posible saldo insuficiente).")
                    self._last_fail_time = time.time()
                    return

                atr_value = indicators.get('ATRr_14', 0)
                self._stop_loss_price = lp - (atr_value * self.atr_multiplier)

                self._qty, self._entry, self._opened_at, self._in_trade = qty, lp, time.time(), True
                self._trade_closed = False
                
                self.logger.info("="*42)
                self.logger.info(f"🚀 COMPRA EJECUTADA | ${lp:,.2f} | Cant: {qty}")
                self.logger.info(f"   • SL Dinámico: ${self._stop_loss_price:,.2f} (ATR: {atr_value:.4f})")
                self.logger.info("="*42)
                return
            
            if reason:
                log_messages = {
                    "lateral": f"Mercado lateral (ADX: {indicators.get('ADX_14', 0):.2f})",
                    "rsi_overbought": f"Sobrecompra (RSI: {indicators.get('RSI_14', 0):.2f})",
                    "low_volume": "Bajo volumen de confirmación"
                }
                if reason in log_messages:
                    self.logger.info(f"Compra rechazada: {log_messages[reason]}.")

            close_reason = self._should_close(price)
            if close_reason and not self._trade_closed:
                self.om.market_sell(f"{self._qty:.8f}")
                
                pnl = (price - self._entry) * self._qty
                result = "GANANCIA 🎉" if pnl > 0 else "PÉRDIDA ⚠️"
                
                self.logger.info("="*42)
                self.logger.info(f"💰 VENTA ({close_reason.upper()}) | {result}")
                self.logger.info(f"   • PnL: {pnl:+.2f} USDT")
                self.logger.info("="*42)

                if self.trade_logger:
                    try:
                        balance = self.om.get_balance("USDT")
                        inv_amt = self._entry * self._qty
                        self.trade_logger.log_trade(
                            self.symbol, "SELL", close_reason, price, self._qty, inv_amt, pnl, balance
                        )
                    except Exception as e:
                        self.logger.error(f"Error al registrar trade: {e}")

                self._in_trade, self._qty, self._entry, self._opened_at, self._stop_loss_price = False, 0.0, 0.0, 0.0, 0.0
                self._trade_closed = True
        except Exception as e:
            self.logger.error(f"on_kline error: {e}", exc_info=True)

    def run(self):
        self.md.start(on_kline=self.on_kline)
        self.logger.info("ScalpingStrategy (Avanzada) en ejecución...")
        try:
            while True: time.sleep(1)
        finally:
            self.md.stop()
