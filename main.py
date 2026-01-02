from src.config import load_settings
from src.logger import setup_logger
from src.exchange.bybit_client import BybitClient
from src.market_data.stream import MarketDataStreamer
from src.orders.order_manager import OrderManager
from src.strategy.scalping_simple import ScalpingStrategy
import logging
import time

def main():
    settings = load_settings()
    logger = setup_logger("Main", settings["log_level"])
    
    # Reactivar logging para ver errores reales
    logging.disable(logging.NOTSET)

    logger.info(f"Iniciando bot en modo: {settings['env']}")
    logger.info(f"Endpoint: {settings['rest_endpoint']}")

    # Initialize client
    client = BybitClient(
        api_key=settings["api_key"],
        api_secret=settings["api_secret"],
        rest_endpoint=settings["rest_endpoint"],
        account_type=settings["account_type"],
        is_testnet=settings["is_testnet"],
        is_demo=settings["is_demo"],
    )

    # Validar conexión ESTRICTA
    try:
        logger.info("Probando conexión a API...")
        balances = client.get_wallet_balance(coins=["USDT"])
        logger.info(f"✅ Conexión exitosa. Balance USDT: {balances.get('USDT', 0)}")
    except Exception as e:
        logger.error(f"❌ ERROR CRÍTICO DE CONEXIÓN: {e}")
        logger.error("Verifica tus API KEYS en el archivo .env y que correspondan a TESTNET/MAINNET")
        logger.error("El bot se detendrá para evitar errores en bucle.")
        time.sleep(5) # Dar tiempo a leer el log
        return # Salir limpiamente

    streamer = MarketDataStreamer(client, settings["symbol"], settings["category"])
    order_manager = OrderManager(client, settings["symbol"], settings["category"])

    strat = ScalpingStrategy(
        streamer=streamer,
        order_manager=order_manager,
        symbol=settings["symbol"],
        risk_usdt=settings.get("risk_per_trade_usdt", 5.0),
        tp_pct=settings.get("tp_pct", 0.003),
        sl_pct=settings.get("sl_pct", 0.005),
        max_open_minutes=settings.get("max_open_minutes", 20),
        adx_threshold=settings.get("adx_threshold", 25.0),
        rsi_threshold=settings.get("rsi_threshold", 68.0),
        logger=logger,
    )
    
    logger.info("🚀 Estrategia iniciada. Presiona Ctrl+C para detener.")
    strat.run()

if __name__ == "__main__":
    main()
