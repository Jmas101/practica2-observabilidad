
import os
import time
import json
from datetime import datetime, timezone

import httpx

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from opentelemetry import trace


# ==========================================
# CONFIGURACION DEL GATEWAY
# ==========================================

app = FastAPI(title="TechSolutions - Gateway")

BACKEND_URL = os.getenv(
    "BACKEND_URL",
    "http://backend:8000"
)


# ==========================================
# MIDDLEWARE DE LOGS JSON
# ==========================================

@app.middleware("http")
async def registrar_logs(request: Request, call_next):

    inicio = time.perf_counter()
    codigo_estado = 500
    tipo_error = None

    try:
        respuesta = await call_next(request)
        codigo_estado = respuesta.status_code
        return respuesta

    except Exception as exc:
        tipo_error = type(exc).__name__
        raise

    finally:
        duracion = time.perf_counter() - inicio

        ruta_objeto = request.scope.get("route")
        ruta = (
            ruta_objeto.path
            if ruta_objeto
            else "unmatched"
        )

        # Obtener identificadores de la traza
        contexto = trace.get_current_span().get_span_context()

        trace_id = (
            format(contexto.trace_id, "032x")
            if contexto.is_valid
            else None
        )

        span_id = (
            format(contexto.span_id, "016x")
            if contexto.is_valid
            else None
        )

        # Crear log estructurado
        log = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": (
                "ERROR"
                if codigo_estado >= 500
                else "INFO"
            ),
            "service": "gateway",
            "msg": (
                "http_request_error"
                if codigo_estado >= 500
                else "http_request"
            ),
            "trace_id": trace_id,
            "span_id": span_id,
            "method": request.method,
            "route": ruta,
            "status": codigo_estado,
            "duration_ms": round(duracion * 1000, 2)
        }

        if tipo_error:
            log["exception_type"] = tipo_error

        print(json.dumps(log), flush=True)


# ==========================================
# ENDPOINT PRINCIPAL
# ==========================================

@app.get("/")
async def inicio():
    return {
        "mensaje": "Bienvenido a TechSolutions",
        "aplicacion": "Gestion de citas medicas",
        "servicio": "gateway"
    }


# ==========================================
# HEALTHCHECK
# ==========================================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "gateway"
    }


# ==========================================
# COMUNICACION CON EL BACKEND
# ==========================================

async def llamar_backend(metodo, ruta, datos=None):

    try:
        async with httpx.AsyncClient(timeout=15.0) as cliente:
            respuesta = await cliente.request(
                metodo,
                f"{BACKEND_URL}{ruta}",
                json=datos
            )

        return JSONResponse(
            status_code=respuesta.status_code,
            content=respuesta.json()
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="El backend no esta disponible"
        )


# ==========================================
# LISTAR CITAS
# ==========================================

@app.get("/citas")
async def listar_citas():
    return await llamar_backend("GET", "/citas")


# ==========================================
# CONSULTAR CITA POR ID
# ==========================================

@app.get("/citas/{cita_id}")
async def obtener_cita(cita_id: int):
    return await llamar_backend(
        "GET",
        f"/citas/{cita_id}"
    )


# ==========================================
# CREAR CITA
# ==========================================

@app.post("/citas")
async def crear_cita(datos: dict):
    return await llamar_backend(
        "POST",
        "/citas",
        datos
    )


# ==========================================
# METRICAS DEL BACKEND
# ==========================================

@app.get("/metrics")
async def obtener_metricas():

    try:
        async with httpx.AsyncClient(timeout=15.0) as cliente:
            respuesta = await cliente.get(
                f"{BACKEND_URL}/metrics"
            )

        return Response(
            content=respuesta.content,
            status_code=respuesta.status_code,
            media_type=respuesta.headers.get(
                "content-type",
                "text/plain"
            )
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Metricas no disponibles"
        )
