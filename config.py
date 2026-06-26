"""
config.py — Parámetros globales del bot
Equivalente a variables de entorno / constants en React
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Credenciales (desde .env) ─────────────────────────
API_KEY    = os.getenv("API_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")

TESTNET    = True  # Usar Binance Futures Testnet por defecto

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Pares a operar ────────────────────────────────────
PARES = ["BTC/USDT", "ETH/USDT","SOL/USDT","XRP/USDT"]   # Agregar más pares aquí si se desea

# ── Capital ───────────────────────────────────────────
SALDO_TOTAL          = 100.0   # Saldo ficticio inicial
PORCENTAJE_POR_TRADE = 0.20    # 8% del saldo por operación por par (conservador con x5)

# ── Futuros ───────────────────────────────────────────
APALANCAMIENTO   = 5
STOP_LOSS_PCT    = 0.005   # Ya no se usa como fijo, se reemplaza por lógica ATR en trader.py, pero lo mantenemos como default/fallback
TAKE_PROFIT_PCT  = 0.010   # 1.0%  → real ~5.0% con x5

# ── Estrategia ────────────────────────────────────────
TIMEFRAME_SEÑAL  = "3m"    # Velas para señal de entrada (antes 1m)
TIMEFRAME_TENDENCIA = "5m" # Velas para filtro de tendencia macro
VELAS_LIMITE     = 100     # Cuántas velas históricas pedir
EMA_RAPIDA       = 9
EMA_LENTA        = 21
RSI_PERIODO      = 14
ATR_PERIODO      = 14
ADX_PERIODO      = 14     # Periodo del ADX
ADX_MIN          = 25     # Umbral de tendencia fuerte
VOLUMEN_MULT_MIN = 1.2    # Volumen > 1.2x del promedio para entrar
RSI_MAX_LONG     = 65      # No entrar long si RSI >= este valor
RSI_MIN_SHORT    = 35      # No entrar short si RSI <= este valor

# ── Gestión de tiempo ─────────────────────────────────
# ── Take Profit parcial ──────────────────────────────
TP_PARCIAL_PCT     = 0.005  # 0.5% → activa el TP parcial (ajustado para x5)
TP_PARCIAL_RATIO   = 0.50   # Cierra el 50% de la posición al llegar al TP parcial

TIEMPO_MIN_CRUCE   = 300   # Segundos mínimos en posición antes de salir por cruce
INTERVALO_LOOP     = 10    # Segundos entre cada ciclo de análisis
INTERVALO_REPORTE  = 3600  # Segundos entre reportes periódicos (1 hora)