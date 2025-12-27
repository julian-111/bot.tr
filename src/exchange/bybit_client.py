from pybit.unified_trading import HTTP
from src.logger import logger

class BybitClient:
    def __init__(self, api_key=None, api_secret=None, is_testnet=None, is_demo=None, rest_endpoint=None, account_type=None):
        self.api_key = api_key if api_key is not None else BYBIT_API_KEY
        self.api_secret = api_secret if api_secret is not None else BYBIT_API_SECRET
        self.is_testnet = is_testnet if is_testnet is not None else BYBIT_TESTNET
        self.is_demo = is_demo if is_demo is not None else BYBIT_DEMO
        
        logger.info(f"Inicializando BybitClient - Testnet: {self.is_testnet}, Demo: {self.is_demo}")
        
        try:
            self.http = HTTP(
                testnet=self.is_testnet,
                demo=self.is_demo,
                api_key=self.api_key,
                api_secret=self.api_secret,
                timeout=25,
                recv_window=50000,
            )
            logger.info("Cliente HTTP de Bybit inicializado correctamente")
        except Exception as e:
            logger.error(f"Error al inicializar cliente HTTP de Bybit: {e}")
            raise

    def get_wallet_balance(self, coins=None):
        try:
            response = self.http.get_wallet_balance(accountType="UNIFIED", coin=",".join(coins) if coins else None)
            
            if response.get('retCode') != 0:
                logger.error(f"Error de API al obtener balance: {response}")
                return {}
                
            result = response.get('result', {})
            list_accounts = result.get('list', [])
            
            balances = {}
            if list_accounts:
                account = list_accounts[0]
                for coin_data in account.get('coin', []):
                    coin_name = coin_data.get('coin')
                    wallet_balance = float(coin_data.get('walletBalance', 0))
                    balances[coin_name] = wallet_balance
                    
            return balances

        except Exception as e:
            logger.error(f"Excepción al obtener balance: {e}")
            raise

    def get_ticker(self, symbol, category="spot"):
        """Obtiene el precio actual (ticker) de un símbolo."""
        try:
            response = self.http.get_tickers(category=category, symbol=symbol)
            
            if response.get('retCode') != 0:
                logger.error(f"Error API al obtener ticker: {response}")
                return None
                
            result = response.get('result', {})
            list_tickers = result.get('list', [])
            
            if list_tickers:
                # Retornamos el primer ticker de la lista
                return list_tickers[0]
            return None
            
        except Exception as e:
            logger.error(f"Excepción al obtener ticker: {e}")
            return None

    def get_symbol_filters(self, symbol, category="spot"):
        """Obtiene filtros del símbolo (decimales de precio, cantidad mínima, etc)."""
        try:
            response = self.http.get_instruments_info(category=category, symbol=symbol)
            if response.get("retCode") != 0:
                logger.error(f"Error obteniendo info de instrumento: {response}")
                return None
            
            result = response.get("result", {})
            lista = result.get("list", [])
            if not lista:
                return None
            
            info = lista[0]
            lot_size = info.get("lotSizeFilter", {})
            price_filter = info.get("priceFilter", {})
            
            return {
                "qty_step": float(lot_size.get("qtyStep", 0)),
                "min_qty": float(lot_size.get("minOrderQty", 0)),
                "max_qty": float(lot_size.get("maxOrderQty", 0)),
                "min_notional": float(lot_size.get("minOrderAmt", 0)), # Agregado para soportar validación de monto mínimo
                "price_tick": float(price_filter.get("tickSize", 0)),
                "min_price": float(price_filter.get("minPrice", 0)),
                "max_price": float(price_filter.get("maxPrice", 0)),
            }
        except Exception as e:
            logger.error(f"Excepción obteniendo filtros: {e}")
            return None

    def get_min_order_value(self, symbol, category="spot"):
        """
        Obtiene el valor mínimo de orden (minNotional o minOrderAmt) para el símbolo.
        Útil para validar compras Market en USDT.
        """
        filters = self.get_symbol_filters(symbol, category)
        if filters:
            return filters.get("min_notional", 0.0)
        return 0.0

    def place_order(self, category, symbol, side, order_type, qty=None, price=None, time_in_force="GTC", stop_loss=None, take_profit=None, **kwargs):
        try:
            order_params = {
                "category": category,
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "timeInForce": time_in_force,
            }
            if qty:
                order_params["qty"] = str(qty)
            if price:
                order_params["price"] = str(price)
            if stop_loss:
                order_params["stopLoss"] = str(stop_loss)
            if take_profit:
                order_params["takeProfit"] = str(take_profit)
            
            # Agregar cualquier otro parámetro extra (marketUnit, quoteOrderQty, etc.)
            order_params.update(kwargs)

            logger.info(f"Enviando orden: {order_params}")
            response = self.http.place_order(**order_params)

            # Si hay un error en la respuesta de la API, lo registramos de forma clara
            if response.get('retCode') != 0:
                logger.error(f"Error de API al enviar orden: {response.get('retMsg')} (retCode: {response.get('retCode')})")
            
            return response
        except Exception as e:
            logger.error(f"Excepción al enviar orden: {e}")
            # Devolvemos un diccionario con el error para un manejo consistente
            return {"retCode": -1, "retMsg": str(e)}

    def get_executions(self, symbol: str, category: str = "spot", orderId: str = None, limit: int = 50):
        try:
            params = {"category": category, "symbol": symbol, "limit": limit}
            if orderId:
                params["orderId"] = orderId
            return self.http.get_executions(**params)
        except Exception as e:
            logger.error(f"Error en get_executions: {e}")
            return {}
