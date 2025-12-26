import threading
import time
import sys
from typing import Optional, Callable
from pybit.unified_trading import WebSocket
from src.logger import setup_logger
from src.exchange.bybit_client import BybitClient

# --- Custom Hook para silenciar errores ruidosos de WebSocket ---
_original_thread_excepthook = threading.excepthook
_last_ws_error_ts = 0
_is_ws_down = False

def _silent_ws_excepthook(args):
    """
    Captura excepciones de hilos. Si es WebSocketConnectionClosedException,
    imprime un mensaje limpio en lugar del traceback gigante.
    """
    global _last_ws_error_ts, _is_ws_down
    exc_msg = str(args.exc_value)
    exc_type_name = args.exc_type.__name__ if args.exc_type else ""
    
    if "WebSocketConnectionClosedException" in exc_type_name or "Connection is already closed" in exc_msg:
        # Solo avisar si es la primera vez que detectamos la caída
        if not _is_ws_down:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"{timestamp} | WARNING | MarketDataStreamer | SE PERDIÓ LA CONEXIÓN WEBSOCKET. Activando protecciones y modo respaldo...")
            _is_ws_down = True
            _last_ws_error_ts = time.time()
    else:
        _original_thread_excepthook(args)

threading.excepthook = _silent_ws_excepthook
# ----------------------------------------------------------------

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
            return
        
        try:
            self.logger.info("Attempting WebSocket subscription for real-time tickers...")
            self._ws = WebSocket(
                testnet=getattr(self.client, "is_testnet", True),
                channel_type="spot",
                ping_interval=30,  # Aumentado para evitar timeouts
                ping_timeout=10,
                restart_on_error=True  # Auto-reinicio
            )
            
            def cb(msg):
                try:
                    # Detectar recuperación de conexión
                    global _is_ws_down
                    if _is_ws_down:
                        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                        print(f"{timestamp} | INFO | MarketDataStreamer | CONEXIÓN WEBSOCKET RECUPERADA. Operación normal restaurada.")
                        _is_ws_down = False

                    if self._debug_messages < 5:
                        self.logger.info(f"WS message: {msg}")
                        self._debug_messages += 1
                    data = msg.get("data")
                    
                    price_str = None
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
            
            # Watchdog para asegurar que si el WS muere, el REST tome el control
            if self._watchdog_thread is None or not self._watchdog_thread.is_alive():
                self._watchdog_thread = threading.Thread(target=self._watchdog_loop, args=(on_tick,), daemon=True)
                self._watchdog_thread.start()
                
        except Exception as e:
            self.logger.warning(f"WebSocket failed ({e}); falling back to REST polling.")
            self._start_rest_polling(on_tick)

    def _start_rest_polling(self, on_tick: Optional[Callable[[float], None]]):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._poll_loop, args=(on_tick,), daemon=True)
        self._thread.start()

    def _watchdog_loop(self, on_tick: Optional[Callable[[float], None]]):
        stale_secs = 20.0  # Tolerancia aumentada
        while not self._stop.is_set():
            try:
                time.sleep(5)
                # Si estamos usando WS pero no llegan datos hace rato
                if self._ws and (time.time() - self._last_tick_ts) > stale_secs and self._last_tick_ts > 0:
                    self.logger.warning("WS sin actividad reciente. Cambiando a REST Polling.")
                    try:
                        self._ws.exit()
                    except Exception:
                        pass
                    self._ws = None
                    self._start_rest_polling(on_tick)
                    break # Salir del watchdog ya que el REST tiene su propio loop
            except Exception as e:
                self.logger.error(f"Watchdog error: {e}")
                time.sleep(5)

    def _poll_loop(self, on_tick: Optional[Callable[[float], None]]):
        self.logger.info("Iniciando REST polling loop...")
        while not self._stop.is_set():
            try:
                ticker = self.client.get_ticker(symbol=self.symbol, category=self.category)
                if ticker:
                    price_str = ticker.get("lastPrice") or ticker.get("lp") or ticker.get("price")
                    if price_str:
                        price = float(price_str)
                        self._last_price = price
                        self._last_tick_ts = time.time()
                        if on_tick:
                            on_tick(price)
            except Exception as e:
                self.logger.error(f"Error en REST polling: {e}")
            
            time.sleep(3) # Polling cada 3 segundos para no saturar

    def stop(self):
        self._stop.set()
        if self._ws:
            try:
                self._ws.exit()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1)
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=1)
