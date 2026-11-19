
import os
import time
import json
import random
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST
)

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


# ==========================================
# CONFIGURACION DE LA APLICACION
# ==========================================

app = FastAPI(title="TechSolutions - Backend")

DATABASE_URL = os.getenv("DATABASE_URL")
tracer = trace.get_tracer("techsolutions.backend")


# ==========================================
# METRICAS DE PROMETHEUS
# ==========================================

http_requests_total = Counter(
    "http_requests_total",
    "Numero total de peticiones HTTP",
    ["method", "route", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "Duracion de las peticiones HTTP en segundos",
    ["method", "route"]
)

appointments_created_total = Counter(
    "appointments_created_total",
    "Numero total de citas medicas creadas"
)


# ==========================================
# MIDDLEWARE DE METRICAS Y LOGS JSON
# ==========================================

@app.middleware("http")
async def registrar_metricas(request: Request, call_next):
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
        if request.url.path != "/metrics":
            duracion = time.perf_counter() - inicio

            ruta_objeto = request.scope.get("route")
            ruta = (
                ruta_objeto.path
                if ruta_objeto
                else "unmatched"
            )

            # Metricas
            http_requests_total.labels(
                method=request.method,
                route=ruta,
                status=str(codigo_estado)
            ).inc()

            http_request_duration_seconds.labels(
                method=request.method,
                route=ruta
            ).observe(duracion)

            # Contexto de OpenTelemetry
            contexto = trace.get_current_span().get_span_context()

            trace_id = (
                format(contexto.trace_id, "032x")
                if contexto.is_valid else None
            )

            span_id = (
                format(contexto.span_id, "016x")
                if contexto.is_valid else None
            )

            # Log JSON estructurado
            log = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": (
                    "ERROR" if codigo_estado >= 500 else "INFO"
                ),
                "service": "backend",
                "msg": (
                    getattr(
                        request.state,
                        "failure_reason",
                        "http_request_error"
                    )
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

            if hasattr(request.state, "simulated_latency_ms"):
                log["simulated_latency_ms"] = (
                    request.state.simulated_latency_ms
                )

            print(json.dumps(log), flush=True)


# ==========================================
# ENDPOINT DE METRICAS
# ==========================================

@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# ==========================================
# MODELO DE DATOS
# ==========================================

class Cita(BaseModel):
    tipo: str = Field(min_length=1, max_length=50)
    fecha: datetime


# ==========================================
# CONEXION A POSTGRESQL
# ==========================================

def conectar_db():
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        connect_timeout=5
    )


# ==========================================
# REGISTRAR ERRORES EN TRAZAS
# ==========================================

def registrar_error_traza(error):
    span = trace.get_current_span()
    span.record_exception(error)
    span.set_status(
        Status(StatusCode.ERROR, type(error).__name__)
    )


# ==========================================
# SIMULACION DE INCIDENTES
# ==========================================

def simular_incidente(request: Request):
    # Desactivar las simulaciones fuera de desarrollo
    if os.getenv("APP_ENV", "development") != "development":
        return

    try:
        error_rate = float(os.getenv("ERROR_RATE", "0"))
        latency_ms = int(os.getenv("LATENCY_MS", "0"))
    except ValueError:
        error_rate = 0
        latency_ms = 0

    # Limitar los valores de simulacion
    error_rate = max(0, min(100, error_rate))
    latency_ms = max(0, min(10000, latency_ms))

    # Simular una respuesta lenta
    if latency_ms > 0:
        request.state.simulated_latency_ms = latency_ms
        time.sleep(latency_ms / 1000)

    # Simular un error HTTP 500
    if random.random() * 100 < error_rate:
        error = RuntimeError("simulated_backend_failure")

        registrar_error_traza(error)

        request.state.failure_reason = (
            "simulated_backend_failure"
        )

        raise HTTPException(
            status_code=500,
            detail="Fallo simulado del backend"
        )


# ==========================================
# ENDPOINT PRINCIPAL
# ==========================================

@app.get("/")
def inicio():
    return {
        "mensaje": "API de citas medicas funcionando",
        "servicio": "backend"
    }


# ==========================================
# HEALTHCHECK
# ==========================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "backend"
    }


# ==========================================
# COMPROBAR BASE DE DATOS
# ==========================================

@app.get("/ready")
def ready():
    try:
        with conectar_db() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("SELECT 1")

        return {
            "status": "ready",
            "database": "ok"
        }

    except psycopg.Error as error:
        registrar_error_traza(error)

        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible"
        ) from error


# ==========================================
# LISTAR TODAS LAS CITAS
# ==========================================

@app.get("/citas")
def listar_citas(request: Request):

    # Simular errores o latencia si estan activados
    simular_incidente(request)

    try:
        with conectar_db() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT id, tipo, fecha, estado "
                    "FROM citas ORDER BY id"
                )

                citas = cursor.fetchall()

        return {"citas": citas}

    except psycopg.Error as error:
        registrar_error_traza(error)

        raise HTTPException(
            status_code=503,
            detail="No se pudieron consultar las citas"
        ) from error


# ==========================================
# OBTENER UNA CITA POR ID
# ==========================================

@app.get("/citas/{cita_id}")
def obtener_cita(cita_id: int):
    try:
        with conectar_db() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT id, tipo, fecha, estado "
                    "FROM citas WHERE id = %s",
                    (cita_id,)
                )

                cita = cursor.fetchone()

        if cita is None:
            raise HTTPException(
                status_code=404,
                detail="Cita no encontrada"
            )

        return cita

    except psycopg.Error as error:
        registrar_error_traza(error)

        raise HTTPException(
            status_code=503,
            detail="Error al consultar la cita"
        ) from error


# ==========================================
# CREAR CITA CON SPAN MANUAL
# ==========================================

@app.post(
    "/citas",
    status_code=status.HTTP_201_CREATED
)
def crear_cita(cita: Cita):

    with tracer.start_as_current_span(
        "appointments.create"
    ) as span:

        span.set_attribute(
            "appointment.type",
            cita.tipo
        )

        span.set_attribute(
            "appointment.operation",
            "create"
        )

        try:
            with conectar_db() as conexion:
                with conexion.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO citas (tipo, fecha, estado)
                        VALUES (%s, %s, %s)
                        RETURNING id, tipo, fecha, estado
                        """,
                        (
                            cita.tipo,
                            cita.fecha,
                            "pendiente"
                        )
                    )

                    nueva_cita = cursor.fetchone()

            span.set_attribute(
                "appointment.status",
                "created"
            )

            appointments_created_total.inc()

            return nueva_cita

        except psycopg.Error as error:
            registrar_error_traza(error)

            raise HTTPException(
                status_code=503,
                detail="No se pudo crear la cita"
            ) from error
