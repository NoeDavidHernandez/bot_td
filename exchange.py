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


# ── Ejecución de Órdenes Reales ───────────────────────

def configurar_mercado(exchange, simbolo: str):
    """Establece margen aislado y el apalancamiento para el par."""
    try:
        # ccxt requiere que los mercados estén cargados para formatear
        exchange.load_markets()
        try:
            exchange.set_margin_mode('isolated', simbolo)
        except Exception as e:
            # A veces ya está en aislado y tira error, lo ignoramos o imprimimos advertencia
            if 'Margin type already set' not in str(e):
                print(f"⚠️ Nota de margen para {simbolo}: {e}")
                
        exchange.set_leverage(config.APALANCAMIENTO, simbolo)
        print(f"⚙️ {simbolo} configurado a {config.APALANCAMIENTO}x (Aislado)")
    except Exception as e:
        print(f"❌ Error configurando mercado {simbolo}: {e}")


def abrir_posicion(exchange, simbolo: str, direccion: str, monto_usdt: float, precio_actual: float) -> float:
    """
    Calcula la cantidad exacta y lanza orden de Market (Long o Short).
    Retorna la cantidad exacta ejecutada, o 0.0 si falla.
    """
    try:
        # Calcular cantidad base a comprar
        cantidad_bruta = (monto_usdt * config.APALANCAMIENTO) / precio_actual
        
        # Ajustar a la precisión permitida por Binance
        mercado = exchange.market(simbolo)
        cantidad_formateada = exchange.amount_to_precision(simbolo, cantidad_bruta)
        cantidad = float(cantidad_formateada)

        if cantidad <= 0:
            print(f"❌ Cantidad {cantidad} es demasiado pequeña para {simbolo}")
            return 0.0

        side = "buy" if direccion == "long" else "sell"
        
        print(f"🚀 Ejecutando {side.upper()} MARKET en {simbolo} | Cantidad: {cantidad}")
        order = exchange.create_market_order(simbolo, side, cantidad)
        return cantidad
    except Exception as e:
        print(f"❌ Error crítico abriendo posición real en {simbolo}: {e}")
        return 0.0


def cerrar_posicion(exchange, simbolo: str, direccion_original: str, cantidad: float) -> bool:
    """
    Lanza una orden opuesta para cerrar la posición actual.
    """
    try:
        if cantidad <= 0:
            return False
            
        # Para cerrar un LONG hacemos SELL, para cerrar un SHORT hacemos BUY
        side = "sell" if direccion_original == "long" else "buy"
        
        # Ajustar por si acaso, aunque ya debería venir de la orden de entrada
        cantidad_formateada = exchange.amount_to_precision(simbolo, cantidad)
        cantidad = float(cantidad_formateada)
        
        print(f"🛡️ Ejecutando Cierre ({side.upper()} MARKET) en {simbolo} | Cantidad: {cantidad}")
        exchange.create_market_order(simbolo, side, cantidad)
        return True
    except Exception as e:
        print(f"❌ Error crítico cerrando posición real en {simbolo}: {e}")
        return False