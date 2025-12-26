from typing import Optional, Dict, Any, List
from src.logger import setup_logger
from src.exchange.bybit_client import BybitClient
import math
import time


class OrderManager:
    def __init__(self, client: BybitClient, symbol: str, category: str = "spot"):
        self.logger = setup_logger(self.__class__.__name__)
        self.client = client
        self.symbol = symbol
        self.category = category

    def market_buy(self, qty: str, order_link_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Recibe cantidad en BASE asset (BTC).
        Como Bybit V5 Spot Market Buy requiere 'qty' en Quote (USDT),
        convertimos BTC -> USDT usando el precio actual.
        """
        # Parsear cantidad solicitada
        try:
            qty_base = float(qty)
        except Exception:
            qty_base = 0.0

        # Precio actual
        try:
            ticker = self.client.get_ticker(symbol=self.symbol, category=self.category)
            price = float(ticker.get("lastPrice") or ticker.get("lp") or ticker.get("price"))
        except Exception:
            price = 0.0

        if price <= 0:
            self.logger.error("No se pudo obtener precio para convertir Market Buy Base -> Quote.")
            return {}

        # Filtros y mínimos del símbolo (para normalizar la cantidad base antes de convertir)
        filters = self.client.get_symbol_filters(self.symbol, category=self.category)
        
        try:
            min_qty = filters.get("min_qty", 0.0) if isinstance(filters, dict) else 0.0
        except Exception:
            min_qty = 0.0
        try:
            qty_step = filters.get("qty_step", 0.0) if isinstance(filters, dict) else 0.0
        except Exception:
            qty_step = 0.0

        # Redondeo hacia ARRIBA al paso
        if qty_step > 0 and qty_base > 0:
            qty_base = math.ceil(qty_base / qty_step) * qty_step

        # Asegurar mínimo de cantidad
        if qty_base < min_qty:
            qty_base = min_qty

        # Convertir a USDT
        usdt_amount = qty_base * price
        
        self.logger.info(f"Market Buy Base: {qty_base} {self.symbol} => {usdt_amount:.4f} USDT")
        
        return self.market_buy_usdt(usdt_amount, order_link_id)

    def market_buy_usdt(self, usdt_amount: float, order_link_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Realiza compra Market enviando la cantidad en USDT (Quote Coin).
        En Bybit V5 Spot, Market Buy usa 'qty' como monto en Quote Coin.
        """
        try:
            # 1. Validar mínimos (MinNotional)
            try:
                min_notional = self.client.get_min_order_value(self.symbol, category=self.category)
            except Exception:
                min_notional = 1.0 # Default fallback
            
            if min_notional is None:
                 min_notional = 1.0

            if usdt_amount < min_notional:
                self.logger.warning(f"Monto {usdt_amount} < MinNotional {min_notional}. Ajustando a {min_notional}.")
                usdt_amount = min_notional

            # Formatear a 4 decimales para USDT
            qty_str = f"{usdt_amount:.4f}"

            self.logger.info(f"Enviando Market Buy: {qty_str} USDT (Quote Amt)")

            return self.client.place_order(
                symbol=self.symbol,
                side="Buy",
                order_type="Market",
                qty=qty_str,
                category=self.category,
                order_link_id=order_link_id,
            )
            
        except Exception as e:
            self.logger.error(f"Error en market_buy_usdt: {e}")
            return {}

    def last_fill(self, order_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recupera la información de ejecución (fill) de una orden recién enviada.
        """
        try:
            # 1. Extraer Order ID
            # La respuesta de place_order suele ser: {'retCode': 0, 'result': {'orderId': '...', 'orderLinkId': '...'}, ...}
            # O directamente el dict si el cliente lo procesa.
            
            result = order_response.get("result", {}) if isinstance(order_response, dict) else {}
            order_id = result.get("orderId")
            
            if not order_id:
                # Intentar buscar en el nivel superior si el cliente aplanó la respuesta
                order_id = order_response.get("orderId")
            
            if not order_id:
                # self.logger.warning(f"No se encontró orderId en la respuesta: {order_response}")
                return {}

            # 2. Consultar ejecuciones (fills)
            # Pequeño delay para dar tiempo al matching engine
            time.sleep(0.5)
            
            # Corregido: pasar 'orderId' (camelCase) coincidiendo con la definición en BybitClient
            executions = self.client.get_executions(symbol=self.symbol, category=self.category, orderId=order_id)
            
            # executions structure: {'retCode': 0, 'result': {'list': [...], ...}}
            # Ojo: si get_executions devuelve directo el dict result, ajustamos.
            # En bybit_client.py: return self.session.get_executions(...)
            # Pybit suele devolver estructura completa.
            
            if isinstance(executions, dict):
                 exec_list = executions.get("result", {}).get("list", [])
                 # Fallback si pybit devuelve directo el result (depende version)
                 if not exec_list and "list" in executions:
                     exec_list = executions["list"]
            else:
                 exec_list = []
            
            if exec_list:
                # Retornamos el primer fill (o el más reciente)
                return exec_list[0]
            
            self.logger.warning(f"No se encontraron ejecuciones para OrderID {order_id}")
            return {}
            
        except Exception as e:
            self.logger.error(f"Error en last_fill: {e}")
            return {}

    def _normalize_qty_base(self, qty_base: float, round_mode: str = "ceil"):
        """
        Normaliza cantidad en moneda base respetando filtros del símbolo.
        """
        # Precio actual
        try:
            ticker = self.client.get_ticker(symbol=self.symbol, category=self.category)
            price = float(ticker.get("lastPrice") or ticker.get("lp") or ticker.get("price"))
        except Exception:
            price = None

        # Filtros y mínimos del símbolo
        filters = self.client.get_symbol_filters(self.symbol, category=self.category)
        lot = filters.get("lotSizeFilter", {}) if isinstance(filters, dict) else {}

        try:
            min_qty = float(lot.get("minOrderQty") or 0)
        except Exception:
            min_qty = 0.0
        try:
            qty_step = float(lot.get("qtyStep") or 0)
        except Exception:
            qty_step = 0.0
        try:
            precision = int(lot.get("basePrecision") or 6)
        except Exception:
            precision = 6

        try:
            min_notional = self.client.get_min_order_value(self.symbol, category=self.category)
        except Exception:
            min_notional = 0.0

        # Redondeo al paso según modo
        if qty_step > 0 and qty_base > 0:
            if round_mode == "ceil":
                qty_base = math.ceil(qty_base / qty_step) * qty_step
            else:
                qty_base = math.floor(qty_base / qty_step) * qty_step

        # Asegurar mínimo de cantidad
        if round_mode == "ceil" and qty_base < min_qty:
            qty_base = min_qty

        # Ajuste por mínimo nocional
        if round_mode == "ceil" and price and price > 0 and min_notional and min_notional > 0:
            notional = qty_base * price
            if notional < min_notional:
                needed_base = min_notional / price
                if qty_step > 0:
                    qty_base = math.ceil(needed_base / qty_step) * qty_step
                else:
                    qty_base = needed_base
                if qty_base < min_qty:
                    qty_base = min_qty

        return qty_base, price, min_notional, min_qty, qty_step, precision

    def market_sell(self, qty: str, order_link_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Vende Market normalizando la cantidad base (BTC).
        En Bybit V5 Spot, Market Sell usa 'qty' como monto en Base Coin.
        """
        # Parseo de qty en base
        try:
            requested_qty = float(qty)
        except Exception:
            requested_qty = 0.0

        # Balance disponible del activo base
        base_coin = self.symbol.replace("USDT", "")
        try:
            balance = self.client.get_wallet_balance(coin=base_coin)
            # Asumimos que get_wallet_balance devuelve float o dict.
            # Ajustar según implementación real de BybitClient.get_wallet_balance
            # Si devuelve dict completo, extraer 'free'.
            if isinstance(balance, dict):
                 # Depende de la estructura de respuesta. 
                 # En bybit_client.py get_wallet_balance suele devolver dict de monedas.
                 # Asumiremos que el cliente maneja la lógica o devolvemos un float si está simplificado.
                 # Si no, intentamos extraer.
                 avail = float(balance.get("transferBalance") or balance.get("walletBalance") or 0)
                 # En Unified Trading Account: walletBalance.
            else:
                 avail = float(balance)
        except Exception:
            avail = 999999.0 # Fallback si falla balance check (riesgoso pero permite intentar)

        # Normalizar
        qty_base, _, _, _, _, precision = self._normalize_qty_base(requested_qty, round_mode="floor")

        # Verificar balance (opcional pero recomendado)
        # if qty_base > avail:
        #    qty_base = avail 
        # (Comentado para no bloquear si el balance check falla)

        qty_str = format(qty_base, f".{precision}f")
        
        self.logger.info(f"Market Sell Base: {qty_str}")

        return self.client.place_order(
            symbol=self.symbol,
            side="Sell",
            order_type="Market",
            qty=qty_str,
            category=self.category,
            order_link_id=order_link_id,
        )
