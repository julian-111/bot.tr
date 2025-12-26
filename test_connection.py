from pybit.unified_trading import HTTP
import os
from dotenv import load_dotenv

# Cargar variables del .env
load_dotenv()

api_key = os.getenv("BYBIT_API_KEY")
api_secret = os.getenv("BYBIT_API_SECRET")

print("--- DIAGNÓSTICO DE API KEY ---")

if not api_key or not api_secret:
    print("❌ Error: No se encontraron BYBIT_API_KEY o BYBIT_API_SECRET en el archivo .env")
    print("Asegúrate de tener el archivo .env creado con tus claves.")
    exit(1)

print(f"🔑 Clave detectada: {api_key[:4]}...{api_key[-4:]}")

# ---------------------------------------------------------
# PRUEBA 1: TESTNET
# ---------------------------------------------------------
print("\n📡 1. Intentando conectar a TESTNET (Dinero Ficticio)...")
try:
    session = HTTP(testnet=True, api_key=api_key, api_secret=api_secret)
    resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
    
    if resp.get("retCode") == 0:
        print("✅ ¡ÉXITO! Esta API Key es de TESTNET.")
        balance = resp['result']['list'][0]['coin'][0]['walletBalance']
        print(f"💰 Balance: {balance} USDT")
    else:
        print(f"❌ No es Testnet. Mensaje: {resp.get('retMsg')}")
except Exception as e:
    print(f"❌ Error técnico en Testnet: {e}")

# ---------------------------------------------------------
# PRUEBA 2: MAINNET (PRODUCCIÓN)
# ---------------------------------------------------------
print("\n📡 2. Intentando conectar a MAINNET (Dinero Real)...")
try:
    session = HTTP(testnet=False, api_key=api_key, api_secret=api_secret)
    resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
    
    if resp.get("retCode") == 0:
        print("✅ ¡ÉXITO! Esta API Key es de PRODUCCIÓN (REAL).")
        balance = resp['result']['list'][0]['coin'][0]['walletBalance']
        print(f"💰 Balance: {balance} USDT")
    else:
        print(f"❌ No es Producción. Mensaje: {resp.get('retMsg')}")
except Exception as e:
    print(f"❌ Error técnico en Producción: {e}")

print("\n---------------------------------------------------------")
