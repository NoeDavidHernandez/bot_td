"""
stats.py — Estado global del bot y estadísticas de sesión
Equivalente a un Zustand/Redux store en React.
Cada par tiene su propio sub-estado de posición aislado.
"""
import threading
import time
from datetime import datetime
import config

# ── Lock global para acceso thread-safe ──────────────
lock = threading.Lock()

# ── Control del bot ───────────────────────────────────
control = {
    "bot_activo": False,
    "modo":       "ambos",   # "ambos" | "long" | "short"
    "pares_activos": { par: True for par in config.PARES }
}

# ── Estado por par (se inicializa dinámicamente) ──────
def _posicion_vacia():
    return {
        "abierta":         False,
        "direccion":       None,      # "long" | "short"
        "precio_entrada":  0.0,
        "stop_loss":       0.0,
        "take_profit":     0.0,
        "tiempo_entrada":    0.0,
        "tp_parcial_ok":     False,  # True cuando ya se ejecutó el TP parcial
        "monto_restante":    1.0,    # Fracción del monto aún en juego (1.0 = 100%)
        "cantidad_monedas":  0.0,
        "forzar_cierre":     False,
        "ultimo_precio":     0.0,
        "ultimo_rsi":      0.0,
        "tend_5m":         "─",
    }

posiciones: dict[str, dict] = {
    par: _posicion_vacia()
    for par in config.PARES
}

# ── Estadísticas globales de sesión ───────────────────
sesion = {
    "inicio":              datetime.now().strftime("%d/%m/%Y %H:%M"),
    "saldo":               config.SALDO_TOTAL,
    "saldo_inicial":       config.SALDO_TOTAL,
    "ganancia_total":      0.0,
    "operaciones_totales": 0,
    "racha_actual":        0,
    "max_racha_ganadora":  0,
    "mayor_ganancia":      0.0,
    "mayor_perdida":       0.0,
    "señales_rechazadas":  0,
    # Desglose por par
    "por_par": {
        par: {
            "totales":   0,
            "ganadoras": 0,
            "ganancia":  0.0,
            "long_totales":   0,
            "long_ganadoras": 0,
            "short_totales":  0,
            "short_ganadoras":0,
        }
        for par in config.PARES
    }
}

historial_operaciones = []
ultimo_reporte = time.time()

logs_entradas = []
logs_generales = []

def agregar_log(mensaje: str, tipo: str = "general"):
    """Agrega un log en memoria y mantiene el límite de 50 elementos."""
    log_obj = {"timestamp": time.time(), "mensaje": mensaje}
    with lock:
        if tipo == "entrada":
            logs_entradas.append(log_obj)
            if len(logs_entradas) > 50:
                logs_entradas.pop(0)
        else:
            logs_generales.append(log_obj)
            if len(logs_generales) > 50:
                logs_generales.pop(0)


# ── Helpers de lectura ────────────────────────────────

def win_rate_global() -> float:
    if sesion["operaciones_totales"] == 0:
        return 0.0
    ganadoras = sum(
        sesion["por_par"][p]["ganadoras"]
        for p in config.PARES
    )
    return ganadoras / sesion["operaciones_totales"] * 100


def rentabilidad() -> float:
    return (sesion["saldo"] - sesion["saldo_inicial"]) / sesion["saldo_inicial"] * 100


def posiciones_abiertas() -> list[str]:
    """Retorna lista de pares con posición activa."""
    return [p for p in config.PARES if posiciones[p]["abierta"]]


# ── Mutaciones ────────────────────────────────────────

def registrar_cierre(par: str, resultado_neto: float, direccion: str):
    """Actualiza todas las estadísticas al cerrar una operación."""
    sesion["saldo"]               += resultado_neto
    sesion["ganancia_total"]      += resultado_neto
    sesion["operaciones_totales"] += 1
    
    historial_operaciones.append({
        "timestamp": time.time(),
        "par": par,
        "ganancia": resultado_neto,
        "ganadora": resultado_neto >= 0,
        "direccion": direccion
    })

    par_stats = sesion["por_par"][par]
    par_stats["totales"]  += 1
    par_stats["ganancia"] += resultado_neto

    if resultado_neto >= 0:
        par_stats["ganadoras"] += 1
        sesion["racha_actual"] = max(sesion["racha_actual"] + 1, 1)
        sesion["max_racha_ganadora"] = max(
            sesion["max_racha_ganadora"], sesion["racha_actual"]
        )
        if resultado_neto > sesion["mayor_ganancia"]:
            sesion["mayor_ganancia"] = resultado_neto
    else:
        sesion["racha_actual"] = min(sesion["racha_actual"] - 1, -1)
        if resultado_neto < sesion["mayor_perdida"]:
            sesion["mayor_perdida"] = resultado_neto

    if direccion == "long":
        par_stats["long_totales"] += 1
        if resultado_neto >= 0:
            par_stats["long_ganadoras"] += 1
    else:
        par_stats["short_totales"] += 1
        if resultado_neto >= 0:
            par_stats["short_ganadoras"] += 1