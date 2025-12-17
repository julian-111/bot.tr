from src.config import load_settings
from src.logger import setup_logger
from src.exchange.bybit_client import BybitClient
from src.market_data.stream import MarketDataStreamer
from src.orders.order_manager import OrderManager
from src.strategy.scalping_simple import ScalpingStrategy
import logging
def main():
    settings = load_settings()
    logger = setup_logger("Main", settings["log_level"])
    # Silenciar todo logging (console) de librerías/módulos; usaremos prints mínimos
    logging.disable(logging.CRITICAL)

    # Initialize client (primer intento con settings actuales)
    client = BybitClient(
        api_key=settings["api_key"],
        api_secret=settings["api_secret"],
        rest_endpoint=settings["rest_endpoint"],
        account_type=settings["account_type"],
        is_testnet=settings["is_testnet"],
        is_demo=settings["is_demo"],
    )

    # Validar conexión: si falla, hacer fallback a TESTNET
    try:
        balances = client.get_wallet_balance(coins=["USDT", "BTC"])
        # Print mínimo de conexión OK (sin detalles)
        print("✅ API conectada")
    except Exception as e:
        print("❌ API fallo; usando TESTNET")
        logger.error(f"No se pudo validar balance (continuaré con datos de mercado): {e}")
        if settings.get("is_demo", False):
            logger.warning("Fallo en DEMO. Cambiando a TESTNET por estabilidad...")
            client = BybitClient(
                api_key=settings["api_key"],
                api_secret=settings["api_secret"],
                rest_endpoint="https://api-testnet.bybit.com",
                account_type=settings["account_type"],
                is_testnet=True,
                is_demo=False,
            )

    streamer = MarketDataStreamer(client, settings["symbol"], settings["category"])
    order_manager = OrderManager(client, settings["symbol"], settings["category"])

    # Ejecutar estrategia mínima

    from src import config as cfg
    strat = ScalpingStrategy(
        streamer=streamer,
        order_manager=order_manager,
        symbol=settings["symbol"],
        risk_usdt=getattr(cfg, "RISK_PER_TRADE_USDT", 10.0),
        tp_pct=getattr(cfg, "TP_PCT", 0.003),
        sl_pct=getattr(cfg, "SL_PCT", 0.005),
        max_open_minutes=getattr(cfg, "MAX_OPEN_MINUTES", 20),
        logger=logger,
    )
    print("Servicio en ejecución. Presiona Ctrl+C para salir.")
    strat.run()

if __name__ == "__main__":
    main()
