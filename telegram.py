"""
telegram.py — Envío de notificaciones y control remoto por comandos
Equivalente a un Context Provider de notificaciones en React
"""
import requests
import time
import threading
from datetime import datetime
import config
import stats

ultimo_update_id = 0


# ── Envío ─────────────────────────────────────────────

def enviar(mensaje: str, tipo: str = "general"):
    stats.agregar_log(mensaje, tipo)
    try:
        url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": config.TELEGRAM_CHAT_ID, "text": mensaje}
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"⚠️ Error Telegram envío: {e}")


# ── Notificaciones de trading ─────────────────────────

def notificar_entrada(par: str, direccion: str, precio: float,
                      monto: float, sl: float, tp: float,
                      rsi: float, vol_ratio: float, adx: float = 0.0):
    emoji = "🚀" if direccion == "long" else "📉"
    dir_txt = "LONG" if direccion == "long" else "SHORT"
    poder = monto * config.APALANCAMIENTO
    # Etiqueta de fuerza ADX para contexto visual
    adx_label = "💪 Fuerte" if adx >= 30 else ("📊 Moderada" if adx >= 20 else "⚠️ Débil")
    enviar(
        f"{emoji} {dir_txt} — {par}\n"
        f"{'─'*26}\n"
        f"💵 Precio: ${precio:.2f}\n"
        f"⚡ x{config.APALANCAMIENTO} | Margen: ${monto:.2f}\n"
        f"💪 Poder: ${poder:.2f}\n"
        f"🎯 TP: ${tp:.2f} | 📉 SL: ${sl:.2f}\n"
        f"📊 RSI: {rsi:.2f} | Vol: {vol_ratio:.2f}x\n"
        f"📈 ADX: {adx:.1f} ({adx_label})\n"
        f"✅ 5m+3m+Vol+ADX OK\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}",
        tipo="entrada"
    )


def notificar_cierre(par: str, tipo: str, direccion: str,
                     precio_entrada: float, precio_salida: float,
                     rendimiento: float, rendimiento_real: float,
                     resultado_neto: float):
    with stats.lock:
        saldo    = stats.sesion["saldo"]
        rent     = stats.rentabilidad()
        wr       = stats.win_rate_global()
        ops      = stats.sesion["operaciones_totales"]
        ganancia = stats.sesion["ganancia_total"]
        activo   = stats.control["bot_activo"]

    emoji_dir = "📈 LONG" if direccion == "long" else "📉 SHORT"
    enviar(
        f"{tipo} — {emoji_dir} {par}\n"
        f"{'─'*26}\n"
        f"💵 ${precio_entrada:.2f} → ${precio_salida:.2f}\n"
        f"📊 {'+'if rendimiento>=0 else ''}{rendimiento*100:.3f}% "
        f"→ x{config.APALANCAMIENTO}: {'+'if rendimiento_real>=0 else ''}{rendimiento_real*100:.2f}%\n"
        f"💰 {'+'if resultado_neto>=0 else ''}${resultado_neto:.2f}\n"
        f"🏦 Saldo: ${saldo:.2f} ({'+'if rent>=0 else ''}{rent:.2f}%)\n"
        f"{'─'*26}\n"
        f"Ops: {ops} | Win: {wr:.1f}% | "
        f"P&L: {'+'if ganancia>=0 else ''}${ganancia:.2f}\n"
        f"Bot: {'🟢' if activo else '🔴'} | "
        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
    )


def notificar_senal_bloqueada(par: str, tipo: str, motivo: str,
                               precio: float, rsi: float, vol_ratio: float):
    with stats.lock:
        bloqueadas = stats.sesion["señales_rechazadas"]
    enviar(
        f"🚫 SEÑAL {tipo} BLOQUEADA — {par}\n"
        f"Motivo: {motivo}\n"
        f"💵 ${precio:.2f} | RSI: {rsi:.2f} | Vol: {vol_ratio:.2f}x\n"
        f"🔢 Bloqueadas sesión: {bloqueadas}"
    )


def notificar_trailing_sl(par: str, direccion: str, sl_viejo: float,
                           sl_nuevo: float, precio: float, ganancia_pct: float):
    if sl_viejo == 0 or abs(sl_nuevo - sl_viejo) / sl_viejo < 0.003:
        return
    emoji = "📈" if direccion == "long" else "📉"
    enviar(
        f"{emoji} TRAILING SL — {par}\n"
        f"  ${sl_viejo:.2f} → ${sl_nuevo:.2f}\n"
        f"  Precio: ${precio:.2f}\n"
        f"  Ganancia asegurada: {ganancia_pct:.2f}%"
    )


def notificar_racha_perdedora():
    with stats.lock:
        racha = stats.sesion["racha_actual"]
        saldo = stats.sesion["saldo"]
    enviar(
        f"🚨 {abs(racha)} PÉRDIDAS CONSECUTIVAS\n"
        f"Saldo: ${saldo:.2f}\n"
        f"Usa /stop para pausar el bot."
    )


def notificar_reporte_periodico():
    with stats.lock:
        saldo  = stats.sesion["saldo"]
        activo = stats.control["bot_activo"]
        modo   = stats.control["modo"]
        rent   = stats.rentabilidad()
        wr     = stats.win_rate_global()
        ops    = stats.sesion["operaciones_totales"]
        ganancia = stats.sesion["ganancia_total"]
        en_pos = stats.posiciones_abiertas()

    modo_txt = {"ambos": "Long & Short", "long": "Solo Long", "short": "Solo Short"}.get(modo)
    pos_txt  = f"🛒 {', '.join(en_pos)}" if en_pos else "🔍 Buscando"

    lineas_par = ""
    for par in config.PARES:
        p = stats.sesion["por_par"][par]
        wr_par = p["ganadoras"] / p["totales"] * 100 if p["totales"] > 0 else 0
        lineas_par += (
            f"  {par}: {p['totales']} ops | "
            f"Win: {wr_par:.0f}% | "
            f"{'+'if p['ganancia']>=0 else ''}${p['ganancia']:.2f}\n"
        )

    enviar(
        f"📊 REPORTE HORARIO\n"
        f"{'─'*26}\n"
        f"🤖 {'🟢' if activo else '🔴'} {modo_txt} | {pos_txt}\n\n"
        f"💼 ${saldo:.2f} ({'+'if rent>=0 else ''}{rent:.2f}%)\n"
        f"💵 P&L: {'+'if ganancia>=0 else ''}${ganancia:.2f}\n\n"
        f"📊 Ops: {ops} | Win: {wr:.1f}%\n"
        f"{lineas_par}"
    )


# ── Comandos ──────────────────────────────────────────

def _construir_status() -> str:
    with stats.lock:
        activo = stats.control["bot_activo"]
        modo   = stats.control["modo"]
        saldo  = stats.sesion["saldo"]
        rent   = stats.rentabilidad()
        wr     = stats.win_rate_global()
        ops    = stats.sesion["operaciones_totales"]
        ganancia = stats.sesion["ganancia_total"]

    modo_txt  = {"ambos": "📊 Long & Short", "long": "📈 Solo Long", "short": "📉 Solo Short"}.get(modo)
    estado_txt = "🟢 ACTIVO" if activo else "🔴 PAUSADO"

    msg = (
        f"📡 STATUS — FUTURES v4\n"
        f"{'─'*28}\n"
        f"🤖 {estado_txt} | {modo_txt}\n\n"
        f"💼 Saldo: ${saldo:.2f} ({'+'if rent>=0 else ''}{rent:.2f}%)\n"
        f"💵 P&L:   {'+'if ganancia>=0 else ''}${ganancia:.2f}\n"
        f"📊 Ops: {ops} | Win: {wr:.1f}%\n"
        f"{'─'*28}\n"
    )

    # Estado por par
    for par in config.PARES:
        with stats.lock:
            pos    = stats.posiciones[par]
            precio = pos["ultimo_precio"]
            rsi    = pos["ultimo_rsi"]
            tend   = pos["tend_5m"]
            en_pos = pos["abierta"]
            direc  = pos["direccion"]
            pe     = pos["precio_entrada"]
            sl     = pos["stop_loss"]
            tp     = pos["take_profit"]
            p_stat = stats.sesion["por_par"][par]

        wr_par = p_stat["ganadoras"] / p_stat["totales"] * 100 if p_stat["totales"] > 0 else 0
        msg += (
            f"{'─'*28}\n"
            f"💰 {par}\n"
            f"  Precio: ${precio:.2f} | RSI: {rsi:.1f}\n"
            f"  5m: {tend}\n"
            f"  Ops: {p_stat['totales']} | Win: {wr_par:.0f}%\n"
        )

        if en_pos and precio > 0:
            if direc == "long":
                pnl = ((precio - pe) / pe) * config.APALANCAMIENTO * 100
            else:
                pnl = ((pe - precio) / pe) * config.APALANCAMIENTO * 100
            emoji_d = "📈 LONG" if direc == "long" else "📉 SHORT"
            msg += (
                f"  🛒 {emoji_d} | Entrada: ${pe:.2f}\n"
                f"  SL: ${sl:.2f} | TP: ${tp:.2f}\n"
                f"  PnL x{config.APALANCAMIENTO}: {'+'if pnl>=0 else ''}{pnl:.2f}%\n"
            )
        else:
            msg += "  🔍 Sin posición\n"

    msg += f"🕐 {datetime.now().strftime('%H:%M:%S')}"
    return msg


def _construir_reporte() -> str:
    with stats.lock:
        saldo    = stats.sesion["saldo"]
        rent     = stats.rentabilidad()
        wr       = stats.win_rate_global()
        ops      = stats.sesion["operaciones_totales"]
        ganancia = stats.sesion["ganancia_total"]
        inicio   = stats.sesion["inicio"]
        mejor    = stats.sesion["mayor_ganancia"]
        peor     = stats.sesion["mayor_perdida"]
        racha    = stats.sesion["max_racha_ganadora"]
        bloq     = stats.sesion["señales_rechazadas"]

    emoji = "📈" if ganancia >= 0 else "📉"
    msg = (
        f"{emoji} REPORTE COMPLETO\n"
        f"{'═'*28}\n"
        f"Sesión: {inicio}\n"
        f"Ahora:  {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"💰 Inicial: ${config.SALDO_TOTAL:.2f}\n"
        f"💰 Actual:  ${saldo:.2f}\n"
        f"📊 Rent.:   {'+'if rent>=0 else ''}{rent:.2f}%\n"
        f"💵 P&L:     {'+'if ganancia>=0 else ''}${ganancia:.2f}\n\n"
        f"📋 GLOBAL\n"
        f"  Ops: {ops} | Win: {wr:.1f}% | 🚫 {bloq}\n\n"
    )
    for par in config.PARES:
        with stats.lock:
            p = stats.sesion["por_par"][par]
        wr_par  = p["ganadoras"] / p["totales"] * 100 if p["totales"] > 0 else 0
        lwr     = p["long_ganadoras"] / p["long_totales"] * 100 if p["long_totales"] > 0 else 0
        swr     = p["short_ganadoras"] / p["short_totales"] * 100 if p["short_totales"] > 0 else 0
        msg += (
            f"{'─'*28}\n"
            f"💰 {par}\n"
            f"  Total: {p['totales']} | Win: {wr_par:.0f}%\n"
            f"  P&L: {'+'if p['ganancia']>=0 else ''}${p['ganancia']:.2f}\n"
            f"  📈 Long:  {p['long_totales']} ops | Win: {lwr:.0f}%\n"
            f"  📉 Short: {p['short_totales']} ops | Win: {swr:.0f}%\n"
        )
    msg += (
        f"{'─'*28}\n"
        f"🏆 Mejor: +${mejor:.2f} | Peor: -${abs(peor):.2f}\n"
        f"🔥 Mejor racha: {racha} ops"
    )
    return msg


def procesar_comando(texto: str) -> str:
    cmd = texto.strip().lower().split()[0]

    if cmd == "/start":
        with stats.lock:
            stats.control["bot_activo"] = True
            stats.control["modo"]       = "ambos"
            saldo = stats.sesion["saldo"]
        return (
            f"✅ BOT ACTIVADO — Long & Short\n"
            f"Pares: {' | '.join(config.PARES)}\n"
            f"⚡ x{config.APALANCAMIENTO} | 💰 ${saldo:.2f}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )

    elif cmd == "/startlong":
        with stats.lock:
            stats.control["bot_activo"] = True
            stats.control["modo"]       = "long"
            saldo = stats.sesion["saldo"]
        return f"✅ Solo LONG activo\nPares: {' | '.join(config.PARES)}\n💰 ${saldo:.2f}"

    elif cmd == "/startshort":
        with stats.lock:
            stats.control["bot_activo"] = True
            stats.control["modo"]       = "short"
            saldo = stats.sesion["saldo"]
        return f"✅ Solo SHORT activo\nPares: {' | '.join(config.PARES)}\n💰 ${saldo:.2f}"

    elif cmd == "/stop":
        with stats.lock:
            if not stats.control["bot_activo"]:
                return "⚠️ El bot ya está pausado."
            stats.control["bot_activo"] = False
            en_pos = stats.posiciones_abiertas()
        if en_pos:
            return (
                f"⏸ BOT PAUSADO\n"
                f"Posiciones abiertas: {', '.join(en_pos)}\n"
                f"Se gestionan hasta SL/TP/Cruce.\n"
                f"Usa /status para monitorear."
            )
        return f"⏸ BOT PAUSADO\nUsa /start para reactivar."

    elif cmd == "/status":
        return _construir_status()

    elif cmd == "/reporte":
        return _construir_reporte()

    elif cmd == "/sl":
        lineas = []
        for par in config.PARES:
            with stats.lock:
                pos    = stats.posiciones[par]
                en_pos = pos["abierta"]
                sl     = pos["stop_loss"]
                tp     = pos["take_profit"]
                pe     = pos["precio_entrada"]
                precio = pos["ultimo_precio"]
                direc  = pos["direccion"]

            if not en_pos:
                lineas.append(f"  {par}: 🔍 Sin posición")
                continue

            dist_sl = abs(precio - sl) / precio * 100
            dist_tp = abs(tp - precio) / precio * 100
            emoji_d = "📈" if direc == "long" else "📉"
            lineas.append(
                f"  {emoji_d} {par}\n"
                f"    Entrada: ${pe:.2f} | Precio: ${precio:.2f}\n"
                f"    SL: ${sl:.2f} ({dist_sl:.2f}%) | TP: ${tp:.2f} ({dist_tp:.2f}%)"
            )
        return "📉 NIVELES ACTUALES\n" + "\n".join(lineas)

    else:
        return (
            f"❓ Comando no reconocido.\n\n"
            f"Disponibles:\n"
            f"  /start /startlong /startshort\n"
            f"  /stop /status /reporte /sl"
        )


# ── Polling thread ────────────────────────────────────

def _obtener_updates() -> list:
    global ultimo_update_id
    try:
        url    = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates"
        params = {"offset": ultimo_update_id + 1, "timeout": 30}
        resp   = requests.get(url, params=params, timeout=35)
        return resp.json().get("result", [])
    except Exception as e:
        print(f"⚠️ Error polling: {e}")
        return []


def iniciar_polling():
    """Lanza el thread de escucha de comandos Telegram."""
    def _loop():
        global ultimo_update_id
        print("📡 Thread Telegram iniciado...")
        while True:
            updates = _obtener_updates()
            for update in updates:
                ultimo_update_id = update["update_id"]
                msg     = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                texto   = msg.get("text", "")

                if not texto or not texto.startswith("/"):
                    continue
                if chat_id != str(config.TELEGRAM_CHAT_ID):
                    print(f"⚠️ Chat no autorizado: {chat_id}")
                    continue

                print(f"\n📨 Comando: {texto}")
                enviar(procesar_comando(texto))
            time.sleep(1)

    hilo = threading.Thread(target=_loop, daemon=True)
    hilo.start()
    return hilo