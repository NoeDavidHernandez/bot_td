"""
exchange.py — Conexión a Binance Futures y obtención de datos OHLCV
Equivalente a un API service en React
"""
import ccxt
import pandas as pd
import pandas_ta as ta
import config


def conectar() -> ccxt.binance | None:
    """Inicializa y verifica la conexión a Binance Futures (Mainnet o Testnet)."""
    exchange_args = {
        "apiKey":    config.API_KEY,
        "secret":    config.SECRET_KEY,
        "enableRateLimit": True,
        "options": {
            "adjustForTimeDifference": True,
            "defaultType": "future",   # Mercado de futuros USDT perpetuos
        },
    }
    
    exchange = ccxt.binance(exchange_args)
    if getattr(config, "TESTNET", False):
        exchange.enable_demo_trading(True)
        print("🔧 MODO TESTNET ACTIVADO (Binance Demo Trading)")

    try:
        exchange.fetch_balance()
        if getattr(config, "TESTNET", False):
            print("✅ Conectado a Binance Futures TESTNET.")
        else:
            print("✅ Conectado a Binance Futures MAINNET.")
        return exchange
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return None


def obtener_velas(exchange, simbolo: str, timeframe: str, limit: int = 100) -> pd.DataFrame | None:
    """
    Descarga velas OHLCV y calcula indicadores técnicos.
    Retorna un DataFrame con las columnas:
      open, high, low, close, volume,
      ema_r, ema_l, rsi, atr, vol_ma
    """
    try:
        ohlcv = exchange.fetch_ohlcv(simbolo, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

        df["ema_r"]  = ta.ema(df["close"], length=config.EMA_RAPIDA)
        df["ema_l"]  = ta.ema(df["close"], length=config.EMA_LENTA)
        df["rsi"]    = ta.rsi(df["close"], length=config.RSI_PERIODO)
        df["atr"]    = ta.atr(
            df["high"], df["low"], df["close"],
            length=config.ATR_PERIODO
        )
        # ADX mide la FUERZA de la tendencia (no la dirección)
        # < 20 = mercado lateral (señales poco confiables)
        # > 25 = tendencia fuerte (señales de alta calidad)
        adx_df    = ta.adx(df["high"], df["low"], df["close"], length=config.ADX_PERIODO)
        df["adx"] = adx_df[f"ADX_{config.ADX_PERIODO}"]

        # shift(1) excluye la vela actual del promedio para evitar ratio artificialmente bajo
        df["vol_ma"] = df["volume"].shift(1).rolling(20).mean()

        return df
    except Exception as e:
        print(f"⚠️ Error obteniendo velas {simbolo} {timeframe}: {e}")
        return None


def obtener_datos_par(exchange, simbolo: str) -> tuple | None:
    """
    Obtiene los datos de ambos timeframes para un par.
    Retorna (vela_tendencia_5m, vela_señal_actual, vela_señal_previa)
    o None si falla cualquier llamada.
    """
    df_tendencia = obtener_velas(
        exchange, simbolo,
        timeframe=config.TIMEFRAME_TENDENCIA,
        limit=50
    )
    df_señal = obtener_velas(
        exchange, simbolo,
        timeframe=config.TIMEFRAME_SEÑAL,
        limit=config.VELAS_LIMITE
    )

    if df_tendencia is None or df_señal is None:
        return None

    return (
        df_tendencia.iloc[-1],   # Vela más reciente en 5m
        df_señal.iloc[-1],       # Vela actual en 3m
        df_señal.iloc[-2],       # Vela previa en 3m (para detectar cruce)
    )