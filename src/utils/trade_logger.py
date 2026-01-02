import csv
import os
from datetime import datetime
from threading import Lock

class TradeLogger:
    def __init__(self, file_path='logs/trades.csv'):
        self._file_path = file_path
        self._lock = Lock()
        self._ensure_header()

    def _ensure_header(self):
        """Asegura que el archivo CSV tenga la cabecera correcta."""
        with self._lock:
            # Crear directorio si no existe
            os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
            
            # Escribir cabecera si el archivo es nuevo o está vacío
            if not os.path.exists(self._file_path) or os.path.getsize(self._file_path) == 0:
                with open(self._file_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "timestamp_utc",
                        "symbol",
                        "side",
                        "reason",
                        "price",
                        "quantity",
                        "investment_usdt",
                        "pnl_usdt",
                        "final_balance_usdt"
                    ])

    def log_trade(self, symbol: str, side: str, reason: str, price: float, quantity: float, investment: float, pnl: float, final_balance: float):
        """
        Registra una operación en el archivo CSV.

        Args:
            symbol (str): Símbolo del activo (ej. "BTCUSDT").
            side (str): "BUY" o "SELL".
            reason (str): Razón del cierre (ej. "TP", "SL", "TIMEOUT").
            price (float): Precio de ejecución.
            quantity (float): Cantidad de activo.
            investment (float): Monto total de la inversión en USDT.
            pnl (float): Ganancia o pérdida de la operación en USDT.
            final_balance (float): Balance total de la cuenta después de la operación.
        """
        with self._lock:
            try:
                with open(self._file_path, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                        symbol,
                        side.upper(),
                        reason.upper(),
                        f"{price:.4f}",
                        f"{quantity:.8f}",
                        f"{investment:.2f}",
                        f"{pnl:.2f}",
                        f"{final_balance:.2f}"
                    ])
            except IOError as e:
                # Manejar errores de escritura si es necesario
                print(f"Error al escribir en el log de trades: {e}")

# Ejemplo de uso (esto no se ejecutará directamente)
if __name__ == '__main__':
    # Esto es solo para demostrar cómo se usaría
    logger = TradeLogger()
    
    # Simular el cierre de una operación ganadora
    logger.log_trade(
        symbol="BTCUSDT",
        side="SELL",
        reason="TP",
        price=70000.0,
        quantity=0.001,
        investment=70.0,
        pnl=0.21,
        final_balance=100.21
    )

    # Simular el cierre de una operación perdedora
    logger.log_trade(
        symbol="BTCUSDT",
        side="SELL",
        reason="SL",
        price=69500.0,
        quantity=0.001,
        investment=70.0,
        pnl=-0.35,
        final_balance=99.86
    )
