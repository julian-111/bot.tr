from typing import Optional, Dict, Any, List
from src.logger import setup_logger
from src.exchange.bybit_client import BybitClient
import math


class OrderManager:
    def __init__(self, client: BybitClient, symbol: str, category: str = "spot"):
        self.logger = setup_logger(self.__class__.__name__)
        self.client = client
        self.symbol = symbol
        self.category = category

    def market_buy(self, qty: str, order_link_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Normaliza la cantidad base (BTC) para cumplir mínimos del símbolo antes de enviar
        una orden Market: redondeo hacia ARRIBA al qtyStep y verificación del nocional final.
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

        # Redondeo hacia ARRIBA al paso para no quedar por debajo por variaciones de precio
        if qty_step > 0 and qty_base > 0:
            qty_base = math.ceil(qty_base / qty_step) * qty_step

        # Asegurar mínimo de cantidad
        if qty_base < min_qty:
            qty_base = min_qty

        # Verificación final del nocional y ajuste si hiciera falta
        if price and price > 0 and min_notional and min_notional > 0:
            notional = qty_base * price
            if notional < min_notional:
                needed_base = min_notional / price
                if qty_step > 0:
                    qty_base = math.ceil(needed_base / qty_step) * qty_step
                else:
                    qty_base = needed_base
                if qty_base < min_qty:
                    qty_base = min_qty

        # Formatear evitando notación científica
        qty_str = format(round(qty_base, precision), f".{precision}f")

        # Log informativo para depurar mínimos
        try:
            self.logger.info(
                f"Normalized buy qty: {qty_str} | "
                f"minNotional≈{min_notional}, minQty={min_qty}, step={qty_step}, precision={precision}, price≈{price}"
            )
        except Exception:
            pass

        return self.client.place_order(
            symbol=self.symbol,
            side="Buy",
            order_type="Market",
            qty=qty_str,
            category=self.category,
            time_in_force="IOC",
            order_link_id=order_link_id,
            # En DEMO algunos parámetros nuevos no existen; sólo marcamos marketUnit en entornos compatibles
            **({ "market_unit": "base" } if not self.client.is_demo else {}),
        )

    def market_buy_usdt(self, usdt_amount: float, order_link_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            min_notional = self.client.get_min_order_value(self.symbol, category=self.category)
        except Exception:
            min_notional = float(usdt_amount)

        base_quote_amt = max(float(usdt_amount), float(min_notional))
        margin = 1.10 if self.client.is_demo and self.category == "spot" else 1.03
        quote_amt = base_quote_amt * margin

        filters = self.client.get_symbol_filters(self.symbol, category=self.category)
        lot = filters.get("lotSizeFilter", {}) if isinstance(filters, dict) else {}
        try:
            quote_precision = int(lot.get("quotePrecision") or 2)
        except Exception:
            quote_precision = 2

        quote_str = format(round(quote_amt, quote_precision), f".{quote_precision}f")

        try:
            self.logger.info(
                f"Market BUY by quote: quoteAmt={quote_str} USDT | minNotional≈{min_notional}, quotePrecision={quote_precision}"
            )
        except Exception:
            pass

        # En DEMO: enviar qty como USDT (sin marketUnit/quoteOrderQty).
        if self.client.is_demo:
            # Limitar al saldo disponible USDT en DEMO para evitar 170131
            try:
                balances = self.client.get_wallet_balance()
                available_usdt = float(balances.get("USDT", 0.0))
                max_quote = max(available_usdt * 0.95, min_notional)
                quote_str = format(min(float(quote_str), max_quote), f".{quote_precision}f")
            except Exception:
                pass
            return self.client.place_order(
                symbol=self.symbol,
                side="Buy",
                order_type="Market",
                qty=quote_str,
                category=self.category,
                time_in_force="IOC",
                order_link_id=order_link_id,
            )

        # En TESTNET/PROD: parámetros modernos de Spot v5.
        return self.client.place_order(
            symbol=self.symbol,
            side="Buy",
            order_type="Market",
            category=self.category,
            market_unit="quote",
            quote_order_qty=quote_str,
            time_in_force="IOC",
            order_link_id=order_link_id,
        )

    def _normalize_qty_base(self, qty_base: float, round_mode: str = "ceil"):
        """
        Normaliza cantidad en moneda base respetando filtros del símbolo.
        round_mode: 'ceil' para compras (no quedarse cortos), 'floor' para ventas (no exceder balance).
        Devuelve (qty_base_normalizada, price, min_notional, min_qty, qty_step, precision).
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

        # Asegurar mínimo de cantidad (solo subir en compras; en ventas lo gestiona quien llama)
        if round_mode == "ceil" and qty_base < min_qty:
            qty_base = min_qty

        # Ajuste por mínimo nocional (solo subir en compras; en ventas lo gestiona quien llama)
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
        Vende Market normalizando la cantidad base para cumplir mínimos del símbolo,
        sin exceder el balance disponible y evitando rechazos por límites bajos.
        """
        # Parseo de qty en base
        try:
            requested_qty = float(qty)
        except Exception:
            requested_qty = 0.0

        # Balance disponible del activo base
        base_coin = self.symbol.replace("USDT", "")
        try:
            balances = self.client.get_wallet_balance()
            available_base = float(balances.get(base_coin, 0.0))
        except Exception:
            available_base = 0.0

        if available_base <= 0:
            raise ValueError(f"Sin balance disponible de {base_coin} para vender.")

        # No vender más de lo disponible
        sell_qty = min(requested_qty, available_base)

        # Normalizar con redondeo hacia ABAJO
        sell_qty, price, min_notional, min_qty, qty_step, precision = self._normalize_qty_base(sell_qty, round_mode="floor")

        # Tras normalizar, no exceder balance (por si precision/paso hacen subir un poco)
        if sell_qty > available_base:
            if qty_step > 0:
                sell_qty = math.floor(available_base / qty_step) * qty_step
            else:
                sell_qty = available_base

        # Validaciones finales de mínimos (si no se cumplen, no enviar para evitar 170140)
        if sell_qty <= 0:
            raise ValueError("Cantidad de venta resultante es 0 tras normalización.")
        if sell_qty < min_qty:
            raise ValueError(f"Cantidad de venta {sell_qty} < minQty {min_qty}. Balance insuficiente para cumplir mínimos.")
        if price and price > 0 and min_notional and min_notional > 0:
            notional = sell_qty * price
            if notional < min_notional:
                raise ValueError(
                    f"Notional de venta {notional:.4f} < mínimo {min_notional}. "
                    f"Balance insuficiente para cumplir mínimos."
                )

        qty_str = format(round(sell_qty, precision), f".{precision}f")

        try:
            self.logger.info(
                f"Normalized sell qty: {qty_str} | "
                f"available={available_base}, minNotional≈{min_notional}, minQty={min_qty}, step={qty_step}, precision={precision}, price≈{price}"
            )
        except Exception:
            pass

        return self.client.place_order(
            symbol=self.symbol,
            side="Sell",
            order_type="Market",
            qty=qty_str,
            category=self.category,
            time_in_force="IOC",
            order_link_id=order_link_id,
        )

    def limit_order(
        self,
        side: str,
        qty: str,
        price: str,
        tif: str = "GTC",
        order_link_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.client.place_order(
            symbol=self.symbol,
            side=side,
            order_type="Limit",
            qty=qty,
            price=price,
            time_in_force=tif,
            category=self.category,
            order_link_id=order_link_id,
        )

    def _round_price_to_tick(self, price: float) -> str:
        filters = self.client.get_symbol_filters(self.symbol, category=self.category)
        pf = filters.get("priceFilter", {}) if isinstance(filters, dict) else {}
        tick = str(pf.get("tickSize") or "0.01")
        try:
            decimals = len(tick.split(".")[1].rstrip("0"))
        except Exception:
            decimals = 2
        # Ajuste al múltiplo del tickSize
        tick_f = float(tick)
        rounded = round(round(price / tick_f) * tick_f, decimals)
        return format(rounded, f".{decimals}f")

    def spot_tpsl_order(
        self,
        side: str,
        qty: str,
        trigger_price: str,
        order_type: str = "Market",
        order_link_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Redondear trigger_price al tick permitido para evitar 170134
        try:
            tp_rounded = self._round_price_to_tick(float(trigger_price))
        except Exception:
            tp_rounded = trigger_price
        return self.client.place_order(
            symbol=self.symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            category=self.category,
            time_in_force="IOC" if order_type == "Market" else "GTC",
            order_link_id=order_link_id,
            order_filter="tpslOrder",
            trigger_price=tp_rounded,
        )

    def cancel(self, order_id: Optional[str] = None, order_link_id: Optional[str] = None) -> Dict[str, Any]:
        return self.client.cancel_order(
            self.symbol,
            order_id=order_id,
            order_link_id=order_link_id,
            category=self.category,
        )

    def open_orders(self) -> List[Dict[str, Any]]:
        return self.client.get_open_orders(self.symbol, category=self.category)

    def executions(self, symbol: str, limit: int = 50):
        return self.client.get_executions(symbol=symbol, category=self.category, limit=limit)

    def last_fill(self, order_response=None) -> Optional[Dict[str, Any]]:
        try:
            ex = self.executions(symbol=self.symbol, limit=5)
            fills = ex.get("result", {}).get("list", []) if isinstance(ex, dict) else []
            return fills[0] if fills else None
        except Exception as e:
            self.logger.warning(f"Error getting last fill: {e}")
            return None
