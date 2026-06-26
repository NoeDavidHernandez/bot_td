"""
strategy.py — Lógica de validación de señales de entrada
Equivalente a custom hooks de lógica de negocio en React
Cada función retorna (es_valida, motivo, vol_ratio)
"""
import config


def _calcular_vol_ratio(vela) -> float:
    """Ratio entre el volumen actual y el promedio de las 20 velas anteriores."""
    if vela["vol_ma"] > 0:
        return vela["volume"] / vela["vol_ma"]
    return 0.0


def validar_long(vela_5m, vela_actual, vela_previa) -> tuple[bool, str, float]:
    """
    Valida si se cumplen los 4 filtros para abrir un LONG.

    Filtros:
      1. Tendencia 5m alcista  — EMA rápida > EMA lenta
      2. Cruce alcista en 3m   — EMA9 cruza arriba EMA21
      3. RSI no sobrecomprado  — RSI < RSI_MAX_LONG
      4. Volumen con respaldo  — vol_ratio > VOLUMEN_MULT_MIN
      5. ADX con fuerza        — ADX > ADX_MIN (mercado en tendencia, no lateral)
    """
    rsi       = vela_actual["rsi"]
    adx       = vela_actual["adx"]
    vol_ratio = _calcular_vol_ratio(vela_actual)

    if not (vela_5m["ema_r"] > vela_5m["ema_l"]):
        return False, "❌ Tendencia 5m bajista", vol_ratio

    cruce_alcista = (
        vela_previa["ema_r"] <= vela_previa["ema_l"] and
        vela_actual["ema_r"]  > vela_actual["ema_l"]
    )
    if not cruce_alcista:
        return False, "❌ Sin cruce alcista en 3m", vol_ratio

    if rsi >= config.RSI_MAX_LONG:
        return False, f"❌ RSI sobrecomprado ({rsi:.1f})", vol_ratio

    if vol_ratio < config.VOLUMEN_MULT_MIN:
        return False, f"❌ Volumen débil ({vol_ratio:.2f}x)", vol_ratio

    # ADX: filtro de mercado lateral — el cruce EMA en rango plano genera whipsaws
    if adx < config.ADX_MIN:
        return False, f"❌ Mercado lateral ADX ({adx:.1f} < {config.ADX_MIN})", vol_ratio

    return True, "✅ OK", vol_ratio


def validar_short(vela_5m, vela_actual, vela_previa) -> tuple[bool, str, float]:
    """
    Valida si se cumplen los 4 filtros para abrir un SHORT.
    Espejo exacto del long con condiciones invertidas.

    Filtros:
      1. Tendencia 5m bajista  — EMA rápida < EMA lenta
      2. Cruce bajista en 3m   — EMA9 cruza abajo EMA21
      3. RSI no sobrevendido   — RSI > RSI_MIN_SHORT
      4. Volumen con respaldo  — vol_ratio > VOLUMEN_MULT_MIN
      5. ADX con fuerza        — ADX > ADX_MIN (mercado en tendencia, no lateral)
    """
    rsi       = vela_actual["rsi"]
    adx       = vela_actual["adx"]
    vol_ratio = _calcular_vol_ratio(vela_actual)

    if not (vela_5m["ema_r"] < vela_5m["ema_l"]):
        return False, "❌ Tendencia 5m alcista", vol_ratio

    cruce_bajista = (
        vela_previa["ema_r"] >= vela_previa["ema_l"] and
        vela_actual["ema_r"]  < vela_actual["ema_l"]
    )
    if not cruce_bajista:
        return False, "❌ Sin cruce bajista en 3m", vol_ratio

    if rsi <= config.RSI_MIN_SHORT:
        return False, f"❌ RSI sobrevendido ({rsi:.1f})", vol_ratio

    if vol_ratio < config.VOLUMEN_MULT_MIN:
        return False, f"❌ Volumen débil ({vol_ratio:.2f}x)", vol_ratio

    # ADX: igual que en long — no operar en mercado sin tendencia clara
    if adx < config.ADX_MIN:
        return False, f"❌ Mercado lateral ADX ({adx:.1f} < {config.ADX_MIN})", vol_ratio

    return True, "✅ OK", vol_ratio


def hay_cruce_potencial_long(vela_actual, vela_previa) -> bool:
    """True si hubo intento de cruce alcista (para notificar bloqueos relevantes)."""
    return (
        vela_previa["ema_r"] <= vela_previa["ema_l"] and
        vela_actual["ema_r"]  > vela_actual["ema_l"]
    )


def hay_cruce_potencial_short(vela_actual, vela_previa) -> bool:
    """True si hubo intento de cruce bajista."""
    return (
        vela_previa["ema_r"] >= vela_previa["ema_l"] and
        vela_actual["ema_r"]  < vela_actual["ema_l"]
    )