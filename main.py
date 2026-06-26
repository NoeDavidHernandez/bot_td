"""
main.py — Entry point del bot
Equivalente a index.tsx en React: orquesta todo pero no contiene lógica.
"""
import time
from datetime import datetime
import config
import stats
import exchange
import trader
import telegram as tg


def _panel_consola(cliente):
    """Muestra estado en consola en una sola línea actualizable."""
    with stats.lock:
        activo = stats.control["bot_activo"]
        saldo  = stats.sesion["saldo"]

    lineas = []
    for par in config.PARES:
        with stats.lock:
            pos    = stats.posiciones[par]
            precio = pos["ultimo_precio"]
            rsi    = pos["ultimo_rsi"]
            tend   = pos["tend_5m"][:2]
            en_pos = pos["abierta"]
            direc  = pos["direccion"]
            pe     = pos["precio_entrada"]
            sl     = pos["stop_loss"]

        if en_pos:
            if direc == "long":
                pnl = ((precio - pe) / pe) * config.APALANCAMIENTO * 100
            else:
                pnl = ((pe - precio) / pe) * config.APALANCAMIENTO * 100
            emoji = "📈" if direc == "long" else "📉"
            lineas.append(f"📈{par} {precio:.2f} SL:{sl:.2f} PnL:{pnl:.2f}%")
        else:
            lineas.append(f"🔍{par} {precio:.2f} RSI:{rsi:.1f} {tend}")


    icono  = "🟢" if activo else "🔴"
    estado = f"{icono} {time.strftime('%H:%M:%S')} | ${saldo:.2f} | " + " | ".join(lineas)
    print(estado, end="\r")


def loop_principal(cliente):
    """Loop principal — itera sobre todos los pares en cada ciclo."""
    print(f"\n🚀 FUTURES PRO v4 — {' | '.join(config.PARES)} | x{config.APALANCAMIENTO}")
    print(f"   Timeframes: {config.TIMEFRAME_SEÑAL} señal + {config.TIMEFRAME_TENDENCIA} tendencia")
    print(f"   Bot en PAUSA. Envía /start en Telegram para activar.\n")

    while True:
        for par in config.PARES:
            datos = exchange.obtener_datos_par(cliente, par)
            if datos is None:
                continue
            vela_5m, vela_actual, vela_previa = datos
            trader.procesar_par(par, vela_5m, vela_actual, vela_previa)

        _panel_consola(cliente)

        # Reporte horario
        with stats.lock:
            diff = time.time() - stats.ultimo_reporte
        if diff >= config.INTERVALO_REPORTE:
            tg.notificar_reporte_periodico()
            with stats.lock:
                stats.ultimo_reporte = time.time()

        time.sleep(config.INTERVALO_LOOP)


def main():
    # 1. Conectar a Binance
    cliente = exchange.conectar()
    if not cliente:
        return

    # 2. Iniciar thread de Telegram
    tg.iniciar_polling()

    # 3. Mensaje de arranque
    monto_por_par = config.SALDO_TOTAL * config.PORCENTAJE_POR_TRADE
    tg.enviar(
        f"⚡ FUTURES BOT v4 — ONLINE\n"
        f"{'─'*26}\n"
        f"📅 {stats.sesion['inicio']}\n"
        f"💰 Pares: {' | '.join(config.PARES)}\n"
        f"🏦 Saldo: ${config.SALDO_TOTAL:.2f}\n"
        f"⚡ Apalancamiento: x{config.APALANCAMIENTO}\n"
        f"💸 Margen/trade/par: ${monto_por_par:.2f}\n"
        f"📊 Timeframes: {config.TIMEFRAME_SEÑAL} + {config.TIMEFRAME_TENDENCIA}\n"
        f"📉 SL: {config.STOP_LOSS_PCT*100:.1f}% | 🎯 TP: {config.TAKE_PROFIT_PCT*100:.1f}%\n"
        f"📦 Vol mín: {config.VOLUMEN_MULT_MIN}x\n"
        f"{'─'*26}\n"
        f"🔴 EN PAUSA — Elige modo:\n"
        f"  /start /startlong /startshort"
    )

    # 4. Iniciar bot en background
    import threading
    import uvicorn
    import os
    
    bot_thread = threading.Thread(target=loop_principal, args=(cliente,), daemon=True)
    bot_thread.start()
    
    # 5. Iniciar servidor web en el hilo principal (requerido para Render)
    port = int(os.environ.get("PORT", 10000))
    print(f"\n🌐 Iniciando servidor web en el puerto {port}...")
    try:
        uvicorn.run("web:app", host="0.0.0.0", port=port, log_level="warning")
    except KeyboardInterrupt:
        print("\n\n⏹ Detenido manualmente.")
        _enviar_resumen_final()
    except Exception as e:
        print(f"\n❌ Error crítico: {e}")
        tg.enviar(f"🚨 ERROR CRÍTICO\n{e}")
        _enviar_resumen_final()


def _enviar_resumen_final():
    with stats.lock:
        saldo = stats.sesion["saldo"]
        rent  = stats.rentabilidad()
        wr    = stats.win_rate_global()
        ops   = stats.sesion["operaciones_totales"]
        gan   = stats.sesion["ganancia_total"]

    tg.enviar(
        f"⏹ BOT DETENIDO\n"
        f"{'─'*24}\n"
        f"Saldo: ${saldo:.2f} ({'+'if rent>=0 else ''}{rent:.2f}%)\n"
        f"Ops: {ops} | Win: {wr:.1f}%\n"
        f"P&L: {'+'if gan>=0 else ''}${gan:.2f}\n"
        f"Pares: {' | '.join(config.PARES)}"
    )


if __name__ == "__main__":
    main()