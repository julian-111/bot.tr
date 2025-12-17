import unittest
from src.exchange.bybit_client import BybitClient
from src.orders.order_manager import OrderManager


class StubHTTP:
    def place_order(self, **kwargs):
        return {"retCode": 0, "retMsg": "OK", "result": {}}
    def get_tickers(self, category, symbol):
        return {"result": {"list": [{"lastPrice": "30000"}]}}
    def get_instruments_info(self, category, symbol):
        return {
            "result": {
                "list": [
                    {
                        "symbol": symbol,
                        "lotSizeFilter": {
                            "minOrderQty": "0.0001",
                            "qtyStep": "0.0001",
                            "basePrecision": 6,
                            "quotePrecision": 2,
                            "minOrderValue": "5"
                        },
                        "priceFilter": {"tickSize": "0.01"},
                    }
                ]
            }
        }
    def get_wallet_balance(self, accountType):
        return {"result": {"list": [{"coin": [{"coin": "USDT", "walletBalance": "100"}]}]}}


class LoadTest(unittest.TestCase):
    def test_normalization_stress(self):
        client = BybitClient(api_key="x", api_secret="y", rest_endpoint="https://api-demo.bybit.com", is_testnet=False, is_demo=True)
        client.http = StubHTTP()
        om = OrderManager(client=client, symbol="BTCUSDT", category="spot")
        # Ejecutar múltiples normalizaciones
        for i in range(5000):
            om.market_buy("0.0003")


if __name__ == "__main__":
    unittest.main()

