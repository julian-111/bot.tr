import threading
import time
from typing import Optional, Callable
from pybit.unified_trading import WebSocket
from src.logger import setup_logger
from src.exchange.bybit_client import BybitClient

class MarketDataStreamer:
    def __init__(self, client: BybitClient, symbol: str, category: str):
        self.logger = setup_logger(self.__class__.__name__)
        self.client = client
        self.symbol = symbol
        self.category = category
        self._last_price: Optional[float] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws: Optional[WebSocket] = None
        self._debug_messages = 0
        self._last_tick_ts: float = 0.0
        self._watchdog_thread: Optional[threading.Thread] = None

    def start(self, on_tick: Optional[Callable[[float], None]] = None):
        if getattr(self.client, "is_demo", False):
            self.logger.info("Demo mode: using REST polling for tickers.")
            self._start_rest_polling(on_tick)
            if self._watchdog_thread is None or not self._watchdog_thread.is_alive():
                self._watchdog_thread = threading.Thread(target=self._watchdog_loop, args=(on_tick,), daemon=True)
                self._watchdog_thread.start()
            return
        
        try:
            self.logger.info("Attempting WebSocket subscription for real-time tickers...")
            self._ws = WebSocket(
                testnet=getattr(self.client, "is_testnet", True),
                channel_type="spot",
            )
            def cb(msg):
                try:
                    if self._debug_messages < 5:
                        self.logger.info(f"WS message: {msg}")
                        self._debug_messages += 1
                    data = msg.get("data")
                    if isinstance(data, list) and data:
                        price_str = (
                            data[0].get("lastPrice")
                            or data[0].get("lp")
                            or data[0].get("last_price")
                            or data[0].get("price")
                        )
                    elif isinstance(data, dict):
                        price_str = (
                            data.get("lastPrice")
                            or data.get("lp")
                            or data.get("last_price")
                            or data.get("price")
                        )
                    else:
                        price_str = None
                    if price_str:
                        price = float(price_str)
                        self._last_price = price
                        self._last_tick_ts = time.time()
                        if on_tick:
                            on_tick(price)
                except Exception as e:
                    self.logger.error(f"Error parsing WS message: {e}")
            self._ws.ticker_stream(symbol=self.symbol, callback=cb)
            self.logger.info("WebSocket ticker stream started.")
            # Iniciar watchdog: si WS queda silente, arrancar polling REST
            if self._watchdog_thread is None or not self._watchdog_thread.is_alive():
                self._watchdog_thread = threading.Thread(target=self._watchdog_loop, args=(on_tick,), daemon=True)
                self._watchdog_thread.start()
        except Exception as e:
            self.logger.warning(f"WebSocket failed ({e}); falling back to REST polling.")
            try:
                if self._ws:
                    self._ws.exit()
            except Exception:
                pass
            self._start_rest_polling(on_tick)

    def _start_rest_polling(self, on_tick: Optional[Callable[[float], None]]):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._poll_loop, args=(on_tick,), daemon=True)
        self._thread.start()

    def _watchdog_loop(self, on_tick: Optional[Callable[[float], None]]):
        # Si no hay ticks WS en N segundos, activar polling REST
        stale_secs = 8.0
        while not self._stop.is_set():
            try:
                last = self._last_tick_ts
                if last == 0.0 or (time.time() - last) > stale_secs:
                    self.logger.warning("WS sin ticks recientes; activando REST polling como respaldo.")
                    try:
                        if self._ws:
                            self._ws.exit()
                            self._ws = None
                    except Exception:
                        pass
                    self._start_rest_polling(on_tick)
                time.sleep(2.0)
            except Exception as e:
                self.logger.error(f"Watchdog error: {e}")
                time.sleep(2.0)

    def _poll_loop(self, on_tick: Optional[Callable[[float], None]]):
        while not self._stop.is_set():
            try:
                ticker = self.client.get_ticker(symbol=self.symbol, category=self.category)
                price_str = ticker.get("lastPrice") or ticker.get("last_price") or ticker.get("lp")
                if price_str:
                    price = float(price_str)
                    self._last_price = price
                    self._last_tick_ts = time.time()
                    if on_tick:
                        on_tick(price)
            except Exception as e:
                self.logger.error(f"REST polling error: {e}")
            time.sleep(1.0)

    def stop(self):
        self._stop.set()
        try:
            if self._ws:
                self._ws.exit()
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=2)
        self.logger.info("MarketDataStreamer stopped.")
