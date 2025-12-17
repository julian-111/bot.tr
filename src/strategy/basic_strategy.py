import time
from typing import Optional
from src.logger import setup_logger
from src.market_data.stream import MarketDataStreamer
from src.orders.order_manager import OrderManager


class BasicStrategy:
    """
    Validación mínima en Demo:
    - Escucha el primer tick y envía una orden Market BUY por monto en USDT.
    - Evita reintentos continuos con un flag interno.
    """

    def __init__(
        self,
        streamer: MarketDataStreamer,
        order_manager: Optional[OrderManager] = None,
        settings: Optional[dict] = None,
        logger=None,
        buy_usdt_amount: Optional[float] = None,
        buy_qty: Optional[float] = None,
    ):
        self.streamer = streamer
        self.md = streamer  # alias esperado por run()
        self.order_manager = order_manager
        self.settings = settings or {}

        # Fallback de logger si no llega
        self.logger = logger if logger is not None else setup_logger("BasicStrategy")

        # Inputs para compra
        self.buy_usdt_amount = buy_usdt_amount
        self.buy_qty = buy_qty
        self.has_bought = False
        self.warned_no_config = False

    def should_buy(self, tick: dict) -> bool:
        # Si no hay monto configurado, no intentar comprar
        if self.buy_usdt_amount is None and self.buy_qty is None:
            return False
        return not self.has_bought

    def on_tick(self, tick: dict):
        try:
            if not self.should_buy(tick):
                return

            if self.order_manager is None:
                self.logger.error("OrderManager no inicializado.")
                return

            # Símbolo desde settings (objeto o dict) con fallback
            symbol = getattr(self.settings, "symbol", None)
            if symbol is None and isinstance(self.settings, dict):
                symbol = self.settings.get("symbol")
            if not symbol:
                symbol = "BTCUSDT"

            # Determinar monto en USDT
            usdt_amount = None
            if self.buy_usdt_amount is not None:
                usdt_amount = float(self.buy_usdt_amount)
            elif self.buy_qty is not None:
                data = tick.get("data", tick) if isinstance(tick, dict) else {}
                lp = data.get("lastPrice")
                if lp is None:
                    self.logger.error("No se pudo obtener lastPrice para convertir buy_qty a USDT.")
                    return
                usdt_amount = float(self.buy_qty) * float(lp)

            if usdt_amount is None:
                if not self.warned_no_config:
                    self.logger.info("BasicStrategy inactiva: sin BUY_USDT_AMOUNT ni buy_qty configurados.")
                    self.warned_no_config = True
                return

            # En Spot v5, Market Buy usa qty como monto en USDT (quote)
            order = self.order_manager.market_buy_usdt(usdt_amount)
            self.logger.info(f"Submitted market buy: {order}")
            self.has_bought = True

        except Exception as e:
            self.logger.error(f"on_tick error: {e}")

    def run(self, runtime_seconds: int = 30):
        self.md.start(on_tick=self.on_tick)
        self.logger.info("Strategy running...")
        try:
            t0 = time.time()
            while time.time() - t0 < runtime_seconds:
                time.sleep(0.5)
        finally:
            self.md.stop()
            self.logger.info("Strategy stopped.")
