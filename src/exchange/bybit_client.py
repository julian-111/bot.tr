from typing import Dict, Any, Optional, List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pybit.unified_trading import HTTP
from pybit.exceptions import FailedRequestError
from pybit.exceptions import InvalidRequestError
from src.logger import setup_logger

class BybitClient:
    def __init__(self, api_key: str, api_secret: str, rest_endpoint: str, account_type: str = "UNIFIED", is_testnet: bool = True, is_demo: bool = False):
        self.logger = setup_logger(self.__class__.__name__)
        self.account_type = account_type
        self.is_testnet = is_testnet
        self.is_demo = is_demo
        # HTTP session for Bybit unified trading
        self.http = HTTP(
            testnet=self.is_testnet,
            demo=self.is_demo,
            api_key=api_key,
            api_secret=api_secret,
            timeout=15,
            recv_window=20000,  # tolerancia para relojes desfasados
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.8, min=1, max=6))
    def get_wallet_balance(self, coins: Optional[List[str]] = None) -> Dict[str, float]:
        # Intenta el tipo de cuenta configurado y cae a alternativas si hay 401
        acct = (self.account_type or "UNIFIED").upper()
        candidates = [acct]
        if acct == "UNIFIED":
            candidates += ["SPOT", "CONTRACT"]
        elif acct == "SPOT":
            candidates += ["UNIFIED", "CONTRACT"]
        else:
            candidates += ["UNIFIED", "SPOT"]

        res = None
        last_err = None
        for a in candidates:
            try:
                self.logger.info(f"Querying wallet-balance with accountType={a} ...")
                res = self.http.get_wallet_balance(accountType=a)
                break
            except FailedRequestError as e:
                self.logger.error(f"Auth error wallet-balance ({a}): {e}")
                last_err = e

        if res is None:
            # Propaga el último error si ninguna variante funcionó
            raise last_err

        balances = {}
        try:
            lists = res.get("result", {}).get("list", [])
            for entry in lists:
                for coin_info in entry.get("coin", []):
                    coin = coin_info.get("coin")
                    bal = float(coin_info.get("walletBalance", "0") or 0)
                    if (not coins) or (coin in coins):
                        balances[coin] = bal
        except Exception as e:
            self.logger.error(f"Failed to parse wallet balance: {e}")
            raise
        self.logger.info(f"Wallet balances: {balances}")
        return balances

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.8, min=1, max=6))
    def get_ticker(self, symbol: str, category: str = "spot") -> Dict[str, Any]:
        res = self.http.get_tickers(category=category, symbol=symbol)
        data = res.get("result", {}).get("list", [])
        if not data:
            raise RuntimeError(f"No ticker data returned for {symbol}")
        return data[0]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.8, min=1, max=6), retry=retry_if_exception_type(FailedRequestError))
    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: Optional[str] = None,
        category: str = "spot",
        price: Optional[str] = None,
        time_in_force: str = "GTC",
        order_link_id: Optional[str] = None,
        reduce_only: Optional[bool] = None,
        market_unit: Optional[str] = None,
        quote_order_qty: Optional[str] = None,
        # TP/SL y filtros Spot v5
        order_filter: Optional[str] = None,
        trigger_price: Optional[str] = None,
        take_profit: Optional[str] = None,
        stop_loss: Optional[str] = None,
        tp_order_type: Optional[str] = None,
        sl_order_type: Optional[str] = None,
        tp_limit_price: Optional[str] = None,
        sl_limit_price: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
        }
        if qty is not None:
            payload["qty"] = qty
        if market_unit:
            payload["marketUnit"] = market_unit
        if quote_order_qty:
            payload["quoteOrderQty"] = quote_order_qty
        if price:
            payload["price"] = price
            payload["timeInForce"] = time_in_force
        if order_link_id:
            payload["orderLinkId"] = order_link_id
        if reduce_only is not None:
            payload["reduceOnly"] = reduce_only
        # Spot TP/SL support
        if order_filter:
            payload["orderFilter"] = order_filter
        if trigger_price:
            payload["triggerPrice"] = trigger_price
        if take_profit:
            payload["takeProfit"] = take_profit
        if stop_loss:
            payload["stopLoss"] = stop_loss
        if tp_order_type:
            payload["tpOrderType"] = tp_order_type
        if sl_order_type:
            payload["slOrderType"] = sl_order_type
        if tp_limit_price:
            payload["tpLimitPrice"] = tp_limit_price
        if sl_limit_price:
            payload["slLimitPrice"] = sl_limit_price

        self.logger.info(f"Placing order: {payload}")
        try:
            res = self.http.place_order(**payload)
        except InvalidRequestError as e:
            self.logger.error(f"Order rejected: {e}")
            raise
        self._assert_ok(res)
        return res

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.8, min=1, max=6))
    def get_open_orders(self, symbol: str, category: str = "spot") -> List[Dict[str, Any]]:
        res = self.http.get_open_orders(category=category, symbol=symbol)
        return res.get("result", {}).get("list", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.8, min=1, max=6))
    def cancel_order(self, symbol: str, order_id: Optional[str] = None, order_link_id: Optional[str] = None, category: str = "spot") -> Dict[str, Any]:
        payload = {
            "category": category,
            "symbol": symbol,
        }
        if order_id:
            payload["orderId"] = order_id
        if order_link_id:
            payload["orderLinkId"] = order_link_id
        res = self.http.cancel_order(**payload)
        self._assert_ok(res)
        return res

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.8, min=1, max=6))
    def get_executions(self, symbol: str, category: str = "spot", limit: int = 50):
        """
        Spot v5: Trade history (executions). Used to detect closes and compute realized PnL.
        """
        res = self.http.get_execution_list(category=category, symbol=symbol, limit=limit)
        return res

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.8, min=1, max=6))
    def get_kline(self, symbol: str, category: str = "spot", interval: str = "1", limit: int = 200) -> List[Dict[str, Any]]:
        res = self.http.get_kline(category=category, symbol=symbol, interval=interval, limit=limit)
        return res.get("result", {}).get("list", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.8, min=1, max=6))
    def get_instruments_info(self, symbol: str, category: str = "spot") -> dict:
        """
        Obtiene el objeto instruments-info del símbolo para conocer filtros y mínimos.
        """
        try:
            resp = self.http.get_instruments_info(category=category, symbol=symbol)
            result = resp.get("result") or {}
            items = result.get("list") or []
            for it in items:
                if it.get("symbol") == symbol:
                    return it
            return items[0] if items else {}
        except Exception as e:
            self.logger.error(f"get_instruments_info error: {e}")
            return {}

    def get_symbol_filters(self, symbol: str, category: str = "spot") -> dict:
        """
        Extrae lotSizeFilter y priceFilter del instruments-info.
        """
        info = self.get_instruments_info(symbol, category=category)
        filters = {}
        if isinstance(info, dict):
            if "lotSizeFilter" in info:
                filters["lotSizeFilter"] = info["lotSizeFilter"]
            if "priceFilter" in info:
                filters["priceFilter"] = info["priceFilter"]
        return filters

    def get_min_order_value(self, symbol: str, category: str = "spot") -> float:
        """
        Determina el mínimo nocional. En demo Spot, fuerza un mínimo conservador si no viene explícito.
        """
        try:
            filters = self.get_symbol_filters(symbol, category=category)
            lot = filters.get("lotSizeFilter", {}) if isinstance(filters, dict) else {}
            mov = lot.get("minOrderValue")
            if mov is not None:
                return float(mov)
            # En Demo Spot, subimos el mínimo efectivo a 20 USDT para evitar rechazos.
            if self.is_demo and category == "spot":
                return 20.0
            min_qty = float(lot.get("minOrderQty") or 0)
            tk = self.get_ticker(symbol=symbol, category=category)
            price_str = tk.get("lastPrice") or tk.get("lp") or tk.get("price")
            price = float(price_str) if price_str else 0.0
            if min_qty > 0 and price > 0:
                return float(min_qty * price)
        except Exception as e:
            self.logger.error(f"get_min_order_value error: {e}")
        # Fallback razonable si todo falla
        return 20.0
    def _assert_ok(self, res: Dict[str, Any]):
        if res.get("retCode") not in (0, "0"):
            code = res.get("retCode")
            msg = res.get("retMsg")
            raise RuntimeError(f"Bybit API error: {code} - {msg}")
