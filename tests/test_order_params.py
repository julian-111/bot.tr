import unittest
from types import SimpleNamespace

from src.exchange.bybit_client import BybitClient
from src.orders.order_manager import OrderManager


class StubHTTP:
    def __init__(self):
        self.last_payload = None

    def place_order(self, **kwargs):
        self.last_payload = kwargs
        # Simula respuesta OK de Bybit
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


class OrderParamsTest(unittest.TestCase):
    def setUp(self):
        self.client = BybitClient(
            api_key="x", api_secret="y", rest_endpoint="https://api-demo.bybit.com", is_testnet=False, is_demo=True
        )
        # Parchear HTTP con stub
        self.client.http = StubHTTP()
        self.om = OrderManager(client=self.client, symbol="BTCUSDT", category="spot")

    def test_demo_market_buy_usdt_no_market_unit(self):
        self.om.market_buy_usdt(22.0)
        payload = self.client.http.last_payload
        self.assertIsNotNone(payload)
        self.assertEqual(payload.get("orderType"), "Market")
        self.assertEqual(payload.get("category"), "spot")
        # qty debe ser monto en USDT y no debe existir marketUnit
        self.assertIn("qty", payload)
        self.assertNotIn("marketUnit", payload)

    def test_assert_ok_raises_on_error(self):
        # Forzar respuesta con error
        class ErrorHTTP(StubHTTP):
            def place_order(self, **kwargs):
                self.last_payload = kwargs
                return {"retCode": 170003, "retMsg": "An unknown parameter was sent.", "result": {}}

        self.client.http = ErrorHTTP()
        with self.assertRaises(RuntimeError):
            self.om.market_buy_usdt(22.0)


if __name__ == "__main__":
    unittest.main()

