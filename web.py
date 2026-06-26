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

@app.get("/api/stats")
def get_stats():
    with stats.lock:
        return {
            "control": stats.control,
            "sesion": stats.sesion,
            "posiciones": stats.posiciones,
            "historial": stats.historial_operaciones
        }

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
    with stats.lock:
        stats.control["bot_activo"] = not stats.control["bot_activo"]
        return {"status": "success", "bot_activo": stats.control["bot_activo"]}

# Asegurar que el directorio static exista
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/", StaticFiles(directory="static", html=True), name="static")
