import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

def load_settings():
    env = os.getenv("BYBIT_ENV", "DEMO").strip().strip('"').strip("'").upper()
    is_demo = env == "DEMO"
    is_testnet = env == "TESTNET"
    is_prod = env == "PROD"
    buy_usdt_amount = os.getenv("BUY_USDT_AMOUNT", "").strip().strip('"').strip("'")

    settings = {
        "api_key": os.getenv("BYBIT_API_KEY", "").strip().strip('"').strip("'"),
        "api_secret": os.getenv("BYBIT_API_SECRET", "").strip().strip('"').strip("'"),
        "account_type": os.getenv("BYBIT_ACCOUNT_TYPE", "UNIFIED"),
        "symbol": os.getenv("SYMBOL", "BTCUSDT"),
        "category": os.getenv("CATEGORY", "spot"),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "env": env,
        "is_demo": is_demo,
        "is_testnet": is_testnet,
        "is_prod": is_prod,
        "buy_usdt_amount": buy_usdt_amount,
        "rest_endpoint": (
            "https://api-demo.bybit.com" if is_demo else (
                "https://api-testnet.bybit.com" if is_testnet else "https://api.bybit.com"
            )
        ),
        "ws_endpoint": (
            "wss://stream.bybit.com" if is_demo else (
                "wss://stream-testnet.bybit.com" if is_testnet else "wss://stream.bybit.com"
            )
        ),
    }
    return settings

# Cargar configuración globalmente
SETTINGS = load_settings()

# EXPORTAR VARIABLES PARA IMPORTACIÓN DIRECTA
BYBIT_API_KEY = SETTINGS["api_key"]
BYBIT_API_SECRET = SETTINGS["api_secret"]
BYBIT_ENV = SETTINGS["env"]
BYBIT_TESTNET = SETTINGS["is_testnet"]
BYBIT_DEMO = SETTINGS["is_demo"]
BYBIT_PROD = SETTINGS["is_prod"]
SYMBOL = SETTINGS["symbol"]
CATEGORY = SETTINGS["category"]
LOG_LEVEL = SETTINGS["log_level"]
BUY_USDT_AMOUNT = SETTINGS["buy_usdt_amount"]
