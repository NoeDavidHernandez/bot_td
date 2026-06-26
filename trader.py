"""
trader.py — Lógica de gestión de posiciones por par (LIVE TRADING HÍBRIDO)
Incluye TP parcial y Trailing SL. Ejecuta órdenes Market reales en Binance.
"""
import time
from datetime import datetime
import config
import stats
import strategy
import telegram as tg
import exchange


def _calcular_rendimiento(pos: dict, precio_actual: float) -> float:
    if pos["direccion"] == "long":
        return (precio_actual - pos["precio_entrada"]) / pos["precio_entrada"]
    else:
        return (pos["precio_entrada"] - precio_actual) / pos["precio_entrada"]


def _actualizar_trailing_sl(par: str, pos: dict, precio: float) -> float:
    sl_actual      = pos["stop_loss"]
    precio_entrada = pos["precio_entrada"]
    tp_parcial_ok  = pos["tp_parcial_ok"]

    if pos["direccion"] == "long":
        nuevo_sl = precio * (1 - config.STOP_LOSS_PCT)
        if tp_parcial_ok:
            nuevo_sl = max(nuevo_sl, precio_entrada)
        if nuevo_sl > sl_actual:
            gan_pct = (nuevo_sl - precio_entrada) / precio_entrada * 100 * config.APALANCAMIENTO
            tg.notificar_trailing_sl(par, "long", sl_actual, nuevo_sl, precio, gan_pct)
            return nuevo_sl
    else:
        nuevo_sl = precio * (1 + config.STOP_LOSS_PCT)
        if tp_parcial_ok:
            nuevo_sl = min(nuevo_sl, precio_entrada)
        if nuevo_sl < sl_actual:
            gan_pct = (precio_entrada - nuevo_sl) / precio_entrada * 100 * config.APALANCAMIENTO
            tg.notificar_trailing_sl(par, "short", sl_actual, nuevo_sl, precio, gan_pct)
            return nuevo_sl

    return sl_actual


def _evaluar_tp_parcial(cliente, par: str, pos: dict, precio: float, monto_total: float) -> bool:
    if pos["tp_parcial_ok"]:
        return False

    rendimiento = _calcular_rendimiento(pos, precio)
    if rendimiento < config.TP_PARCIAL_PCT:
        return False

    # Ejecutar TP parcial (Real)
    fraccion_cerrada  = config.TP_PARCIAL_RATIO
    fraccion_restante = 1.0 - fraccion_cerrada
    cantidad_a_cerrar = pos["cantidad_monedas"] * fraccion_cerrada
    
    # Cerrar en Binance
    exito = exchange.cerrar_posicion(cliente, par, pos["direccion"], cantidad_a_cerrar)
    if not exito:
        return False # Falló el cierre en Binance, reintentar próximo ciclo

    monto_cerrado   = monto_total * fraccion_cerrada
    rend_real       = rendimiento * config.APALANCAMIENTO
    ganancia_parcial = monto_cerrado * rend_real

    if pos["direccion"] == "long":
        sl_post_parcial = precio * (1 - config.STOP_LOSS_PCT)
        sl_post_parcial = max(sl_post_parcial, pos["precio_entrada"])
    else:
        sl_post_parcial = precio * (1 + config.STOP_LOSS_PCT)
        sl_post_parcial = min(sl_post_parcial, pos["precio_entrada"])

    with stats.lock:
        stats.sesion["saldo"]          += ganancia_parcial
        stats.sesion["ganancia_total"] += ganancia_parcial
        stats.posiciones[par]["tp_parcial_ok"]  = True
        stats.posiciones[par]["monto_restante"] = fraccion_restante
        stats.posiciones[par]["cantidad_monedas"] -= cantidad_a_cerrar # Queda la mitad
        stats.posiciones[par]["stop_loss"]      = sl_post_parcial

    tg.enviar(
        f"⚡ TP PARCIAL ({int(fraccion_cerrada*100)}%) — {par}\n"
        f"{'─'*26}\n"
        f"💰 Cerrado {int(fraccion_cerrada*100)}%: +${ganancia_parcial:.3f}\n"
        f"📊 Rend: +{rendimiento*100:.3f}% → x{config.APALANCAMIENTO}: +{rend_real*100:.2f}%\n"
        f"🛡️ SL post-parcial: ${sl_post_parcial:.2f}\n"
        f"🔒 Breakeven garantizado: ${pos['precio_entrada']:.2f}\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
    )
    return True


def _debe_cerrar(pos: dict, precio: float, vela_actual) -> tuple[bool, str]:
    if pos.get("forzar_cierre", False):
        return True, "🔘 CIERRE MANUAL"
        
    tiempo_en_pos = time.time() - pos["tiempo_entrada"]

    if pos["direccion"] == "long":
        if precio >= pos["take_profit"]:
            return True, "🟢 TAKE PROFIT"
        if precio <= pos["stop_loss"]:
            rend = _calcular_rendimiento(pos, precio)
            if pos["tp_parcial_ok"]:
                return True, "🛡️ BREAKEVEN" if rend >= 0 else "🔴 STOP LOSS"
            return True, "🛡️ SALIDA PROTEGIDA" if rend >= 0 else "🔴 STOP LOSS"
        cruce = vela_actual["ema_r"] < vela_actual["ema_l"]
        if cruce and tiempo_en_pos >= config.TIEMPO_MIN_CRUCE:
            return True, "🔄 CRUCE INVERSO"
    else:
        if precio <= pos["take_profit"]:
            return True, "🟢 TAKE PROFIT"
        if precio >= pos["stop_loss"]:
            rend = _calcular_rendimiento(pos, precio)
            if pos["tp_parcial_ok"]:
                return True, "🛡️ BREAKEVEN" if rend >= 0 else "🔴 STOP LOSS"
            return True, "🛡️ SALIDA PROTEGIDA" if rend >= 0 else "🔴 STOP LOSS"
        cruce = vela_actual["ema_r"] > vela_actual["ema_l"]
        if cruce and tiempo_en_pos >= config.TIEMPO_MIN_CRUCE:
            return True, "🔄 CRUCE INVERSO"

    return False, ""


def procesar_par(cliente, par: str, vela_5m, vela_actual, vela_previa):
    with stats.lock:
        bot_activo = stats.control["bot_activo"]
        par_activo = stats.control.get("pares_activos", {}).get(par, True)
        modo       = stats.control["modo"]
        pos        = dict(stats.posiciones[par])
        saldo      = stats.sesion["saldo"]

    precio = vela_actual["close"]
    rsi    = vela_actual["rsi"]
    tend   = "📈 Alcista" if vela_5m["ema_r"] > vela_5m["ema_l"] else "📉 Bajista"

    with stats.lock:
        stats.posiciones[par]["ultimo_precio"] = precio
        stats.posiciones[par]["ultimo_rsi"]    = rsi
        stats.posiciones[par]["tend_5m"]       = tend

    monto_total = saldo * config.PORCENTAJE_POR_TRADE

    if not pos["abierta"] and bot_activo and par_activo:
        _intentar_entrada(cliente, par, modo, monto_total,
                          vela_5m, vela_actual, vela_previa, precio, rsi)
    elif pos["abierta"]:
        _gestionar_posicion(cliente, par, pos, monto_total, precio, vela_actual)


def _intentar_entrada(cliente, par: str, modo: str, monto: float,
                      vela_5m, vela_actual, vela_previa,
                      precio: float, rsi: float):
    
    if modo in ("ambos", "long"):
        valida, motivo, vol_ratio = strategy.validar_long(vela_5m, vela_actual, vela_previa)
        if valida:
            # Ejecutar orden REAL
            cantidad_ejecutada = exchange.abrir_posicion(cliente, par, "long", monto, precio)
            if cantidad_ejecutada > 0:
                import math
                atr = vela_actual.get("atr", float('nan'))
                if math.isnan(atr) or atr <= 0:
                    atr = precio * 0.005
                sl = precio - (atr * 1.5)
                tp = precio * (1 + config.TAKE_PROFIT_PCT)
                with stats.lock:
                    stats.posiciones[par].update({
                        "abierta":        True,
                        "direccion":      "long",
                        "precio_entrada": precio,
                        "stop_loss":      sl,
                        "take_profit":    tp,
                        "tiempo_entrada": time.time(),
                        "tp_parcial_ok":  False,
                        "monto_restante": 1.0,
                        "cantidad_monedas": cantidad_ejecutada,
                        "forzar_cierre": False,
                    })
                tg.notificar_entrada(par, "long", precio, monto, sl, tp, rsi, vol_ratio, vela_actual["adx"])
            return
        elif strategy.hay_cruce_potencial_long(vela_actual, vela_previa):
            with stats.lock:
                stats.sesion["señales_rechazadas"] += 1
            tg.notificar_senal_bloqueada(par, "LONG", motivo, precio, rsi, vol_ratio)

    if modo in ("ambos", "short"):
        valida, motivo, vol_ratio = strategy.validar_short(vela_5m, vela_actual, vela_previa)
        if valida:
            # Ejecutar orden REAL
            cantidad_ejecutada = exchange.abrir_posicion(cliente, par, "short", monto, precio)
            if cantidad_ejecutada > 0:
                import math
                atr = vela_actual.get("atr", float('nan'))
                if math.isnan(atr) or atr <= 0:
                    atr = precio * 0.005
                sl = precio + (atr * 1.5)
                tp = precio * (1 - config.TAKE_PROFIT_PCT)
                with stats.lock:
                    stats.posiciones[par].update({
                        "abierta":        True,
                        "direccion":      "short",
                        "precio_entrada": precio,
                        "stop_loss":      sl,
                        "take_profit":    tp,
                        "tiempo_entrada": time.time(),
                        "tp_parcial_ok":  False,
                        "monto_restante": 1.0,
                        "cantidad_monedas": cantidad_ejecutada,
                        "forzar_cierre": False,
                    })
                tg.notificar_entrada(par, "short", precio, monto, sl, tp, rsi, vol_ratio, vela_actual["adx"])
        elif strategy.hay_cruce_potencial_short(vela_actual, vela_previa):
            with stats.lock:
                stats.sesion["señales_rechazadas"] += 1
            tg.notificar_senal_bloqueada(par, "SHORT", motivo, precio, rsi, vol_ratio)


def _gestionar_posicion(cliente, par: str, pos: dict, monto_total: float,
                        precio: float, vela_actual):
    # 1. Actualizar trailing SL
    nuevo_sl = _actualizar_trailing_sl(par, pos, precio)
    if nuevo_sl != pos["stop_loss"]:
        with stats.lock:
            stats.posiciones[par]["stop_loss"] = nuevo_sl
        pos["stop_loss"] = nuevo_sl

    # 2. Evaluar TP parcial
    if not pos["tp_parcial_ok"]:
        ejecutado = _evaluar_tp_parcial(cliente, par, pos, precio, monto_total)
        if ejecutado:
            with stats.lock:
                pos = dict(stats.posiciones[par])

    # 3. Evaluar cierre del resto de la posición
    debe_cerrar, tipo_cierre = _debe_cerrar(pos, precio, vela_actual)
    if not debe_cerrar:
        return

    # Cerrar en Binance
    exito = exchange.cerrar_posicion(cliente, par, pos["direccion"], pos["cantidad_monedas"])
    if not exito:
        return # Si falla, intenta el próximo ciclo
        
    monto_en_juego   = monto_total * pos["monto_restante"]
    rendimiento      = _calcular_rendimiento(pos, precio)
    rendimiento_real = rendimiento * config.APALANCAMIENTO
    resultado_neto   = monto_en_juego * rendimiento_real

    with stats.lock:
        stats.posiciones[par].update({
            "abierta":        False,
            "direccion":      None,
            "precio_entrada": 0.0,
            "stop_loss":      0.0,
            "take_profit":    0.0,
            "tiempo_entrada": 0.0,
            "tp_parcial_ok":  False,
            "monto_restante": 1.0,
            "cantidad_monedas": 0.0,
            "forzar_cierre": False,
        })
        stats.registrar_cierre(par, resultado_neto, pos["direccion"])
        racha = stats.sesion["racha_actual"]

    tg.notificar_cierre(
        par, tipo_cierre, pos["direccion"],
        pos["precio_entrada"], precio,
        rendimiento, rendimiento_real, resultado_neto
    )

    if racha <= -3:
        tg.notificar_racha_perdedora()