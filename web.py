from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import stats
import os

app = FastAPI(title="Futures Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import config

@app.get("/api/stats")
def get_stats():
    with stats.lock:
        return {
            "control": stats.control,
            "sesion": stats.sesion,
            "posiciones": stats.posiciones,
            "historial": stats.historial_operaciones,
            "logs_entradas": stats.logs_entradas,
            "logs_generales": stats.logs_generales,
            "apalancamiento": config.APALANCAMIENTO
        }

from pydantic import BaseModel

class ClosePositionReq(BaseModel):
    par: str

@app.post("/api/close_position")
def close_position(req: ClosePositionReq):
    with stats.lock:
        if req.par in stats.posiciones and stats.posiciones[req.par]["abierta"]:
            stats.posiciones[req.par]["forzar_cierre"] = True
            return {"status": "success", "msg": f"Cierre manual programado para {req.par}"}
        return {"status": "error", "msg": "Posición no encontrada o ya está cerrada"}

from pydantic import BaseModel

class ToggleParReq(BaseModel):
    par: str

@app.post("/api/toggle_par")
def toggle_par(req: ToggleParReq):
    with stats.lock:
        if req.par in stats.control.get("pares_activos", {}):
            stats.control["pares_activos"][req.par] = not stats.control["pares_activos"][req.par]
            return {"status": "success", "par": req.par, "activo": stats.control["pares_activos"][req.par]}
        return {"status": "error", "msg": "Par no encontrado"}

@app.post("/api/toggle")
def toggle_bot():
    import telegram as tg
    with stats.lock:
        stats.control["bot_activo"] = not stats.control["bot_activo"]
        activo = stats.control["bot_activo"]
        if activo:
            stats.control["modo"] = "ambos"
            
    # Notificar a telegram (y por ende, a los logs de la web)
    estado_txt = "✅ BOT ACTIVADO (Desde la Web)" if activo else "⏸ BOT PAUSADO (Desde la Web)"
    tg.enviar(estado_txt)
    
    return {"status": "success", "bot_activo": activo}

# Asegurar que el directorio static exista
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/", StaticFiles(directory="static", html=True), name="static")
