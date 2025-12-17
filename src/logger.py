import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name: str, level: str = "INFO"):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # prevent duplicate handlers in repeated calls

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    os.makedirs("logs", exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Rotating file
    fh = RotatingFileHandler("logs/bot.log", maxBytes=2_000_000, backupCount=3)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger

def setup_trade_logger(name: str = "Trades"):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # evitar duplicados

    logger.setLevel(logging.INFO)
    os.makedirs("logs", exist_ok=True)

    # Formato “bonito” solo para operaciones
    fmt = logging.Formatter(
        "%(asctime)s | TRADE | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Consola solo con trades
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Asegurar que el archivo exista
    trade_log_path = "logs/trades.log"
    try:
        with open(trade_log_path, "a"):
            pass
    except Exception:
        os.makedirs("logs", exist_ok=True)

    fh = RotatingFileHandler(trade_log_path, maxBytes=1_000_000, backupCount=5)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger