import os
from dotenv import load_dotenv

def load_settings():
    load_dotenv()
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
        "buy_usdt_amount": buy_usdt_amount,
        # Endpoints según entorno
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
    if not settings["api_key"] or not settings["api_secret"]:
        raise ValueError("Missing BYBIT_API_KEY or BYBIT_API_SECRET in .env")
    if len(settings["api_key"]) < 16 or len(settings["api_secret"]) < 30:
        print(
            f"WARNING: Unusual BYBIT_API_KEY/BYBIT_API_SECRET lengths: "
            f"{len(settings['api_key'])}/{len(settings['api_secret'])}. "
            f"Verifica que sean del entorno correcto."
        )
    return settings

# Config esencial
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = os.getenv("CATEGORY", "spot")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
