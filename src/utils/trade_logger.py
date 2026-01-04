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
                        "fecha",
                        "hora",
                        "cantidad de inversion",
                        "ganancia o perdida",
                        "balance actual"
                    ])

    def log_trade(self, symbol: str, side: str, reason: str, price: float, quantity: float, investment: float, pnl: float, final_balance: float):
        """
        Registra una operación en el archivo CSV con el formato solicitado.
        """
        with self._lock:
            try:
                now = datetime.utcnow()
                fecha = now.strftime('%Y-%m-%d')
                hora = now.strftime('%H:%M:%S')
                
                with open(self._file_path, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        fecha,
                        hora,
                        f"{investment:.2f}",
                        f"{pnl:.2f}",
                        f"{final_balance:.2f}"
                    ])
            except IOError as e:
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
