import threading
import time
import sys
from typing import Optional, Callable, Dict
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

        # Banderas de estado para la conexión
        self._is_websocket_connected: bool = False
        self._is_polling_down: bool = False

    def on_open(self, ws):
        self.logger.info("Conexión WebSocket abierta.")
        self._is_websocket_connected = True
        self.subscribe(ws)

    def on_close(self, ws, close_status_code, close_msg):
        if self._is_websocket_connected:
            self.logger.warning(f"Conexión WebSocket cerrada. Código: {close_status_code}, Mensaje: {close_msg}")
            self._is_websocket_connected = False

    def on_error(self, ws, error):
        if "Connection is already closed" in str(error):
            return
        if self._is_websocket_connected:
            self.logger.error(f"Error en WebSocket: {error}")
            self._is_websocket_connected = False

    def start(self, on_kline: Optional[Callable[[Dict], None]] = None):
        if getattr(self.client, "is_demo", False):
            self.logger.info("Demo mode: using REST polling for klines.")
            self._start_rest_polling(on_kline)
            return
        
        try:
            self.logger.info("Attempting WebSocket subscription for real-time klines (1-minute)...")
            self._ws = WebSocket(
                testnet=getattr(self.client, "is_testnet", True),
                channel_type="spot",
                ping_interval=30,
                ping_timeout=10,
                restart_on_error=True,
                on_open=self.on_open,
                on_close=self.on_close,
                on_error=self.on_error
            )
            
            def cb(msg):
                try:
                    global _is_ws_down
                    if _is_ws_down:
                        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                        print(f"{timestamp} | INFO | MarketDataStreamer | CONEXIÓN WEBSOCKET RECUPERADA. Operación normal restaurada.")
                        _is_ws_down = False

                    if self._debug_messages < 5:
                        self.logger.info(f"WS kline message: {msg}")
                        self._debug_messages += 1
                    
                    data = msg.get("data")
                    if isinstance(data, list) and data:
                        kline_data = data[0]
                        # Solo procesar velas confirmadas
                        if kline_data.get('confirm', False):
                            kline = {
                                'timestamp': int(kline_data['start']),
                                'open': float(kline_data['open']),
                                'high': float(kline_data['high']),
                                'low': float(kline_data['low']),
                                'close': float(kline_data['close']),
                                'volume': float(kline_data['volume']),
                            }
                            self._last_price = kline['close']
                            self._last_tick_ts = time.time()
                            if on_kline:
                                on_kline(kline)
                                
                except Exception as e:
                    self.logger.error(f"Error parsing WS kline message: {e}")

            self._ws.kline_stream(interval=1, symbol=self.symbol, callback=cb)
            self.logger.info("WebSocket kline stream started.")
            
            if self._watchdog_thread is None or not self._watchdog_thread.is_alive():
                self._watchdog_thread = threading.Thread(target=self._watchdog_loop, args=(on_kline,), daemon=True)
                self._watchdog_thread.start()
                
        except Exception as e:
            self.logger.warning(f"WebSocket failed ({e}); falling back to REST polling for klines.")
            self._start_rest_polling(on_kline)

    def _start_rest_polling(self, on_kline: Optional[Callable[[Dict], None]]):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._poll_loop, args=(on_kline,), daemon=True)
        self._thread.start()

    def _watchdog_loop(self, on_kline: Optional[Callable[[Dict], None]]):
        stale_secs = 70.0 # 1 minuto + 10s de margen
        while not self._stop.is_set():
            try:
                time.sleep(10)
                if self._ws and (time.time() - self._last_tick_ts) > stale_secs and self._last_tick_ts > 0:
                    self.logger.warning("WS kline stream sin actividad. Cambiando a REST Polling.")
                    try:
                        self._ws.exit()
                    except Exception:
                        pass
                    self._ws = None
                    self._start_rest_polling(on_kline)
                    break
            except Exception as e:
                self.logger.error(f"Watchdog error: {e}")
                time.sleep(5)

    def _poll_loop(self, on_kline: Optional[Callable[[Dict], None]]):
        self.logger.info("Iniciando REST polling loop para klines...")
        last_kline_ts = 0
        while not self._stop.is_set():
            try:
                klines = self.client.get_klines(symbol=self.symbol, category=self.category, interval=1, limit=2)
                if klines and klines['list']:
                    if self._is_polling_down:
                        self.logger.info("Conexión de respaldo (REST Polling) recuperada.")
                        self._is_polling_down = False

                    latest_kline_raw = klines['list'][0]
                    kline_ts = int(latest_kline_raw[0])
                    
                    if kline_ts > last_kline_ts:
                        last_kline_ts = kline_ts
                        kline = {
                            'timestamp': kline_ts,
                            'open': float(latest_kline_raw[1]),
                            'high': float(latest_kline_raw[2]),
                            'low': float(latest_kline_raw[3]),
                            'close': float(latest_kline_raw[4]),
                            'volume': float(latest_kline_raw[5]),
                        }
                        self._last_price = kline['close']
                        self._last_tick_ts = time.time()
                        if on_kline:
                            on_kline(kline)
            except Exception as e:
                if not self._is_polling_down:
                    self.logger.error(f"Se perdió la conexión de respaldo (REST Polling): {e}")
                    self._is_polling_down = True
            
            time.sleep(30)

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
