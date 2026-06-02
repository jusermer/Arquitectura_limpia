"""
interfaces/api/fastapi_app.py

Factory de la aplicación FastAPI.

Responsabilidades:
- Crear y configurar la instancia de FastAPI
- Registrar routers
- Configurar middleware (CORS, logging, manejo de errores)
- Gestionar eventos de startup y shutdown
- Inyectar dependencias de infraestructura

Reglas Clean Architecture:
- Es el punto de entrada de la capa interfaces/
- Ensambla las piezas: repositorios → casos de uso → rutas
- La lógica de negocio NUNCA vive aquí
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.infrastructure.config.settings import settings
from app.interfaces.api.routes_mediciones import router as mediciones_router


# ---------------------------------------------------------------------------
# Lifespan — startup y shutdown de la aplicación
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida de la aplicación.

    startup  → se ejecuta antes de recibir requests
    shutdown → se ejecuta al apagar el servidor

    Aquí se inicializan recursos costosos: conexiones a BD,
    clientes externos, caché, etc.
    """
    # ── Startup ──────────────────────────────────────────────────────
    print(f"[startup] Entorno : {settings.app.entorno}")
    print(f"[startup] Debug   : {settings.app.debug}")
    print(f"[startup] BD      : {settings.db.server} / {settings.db.database}")

    yield  # La aplicación está corriendo y recibiendo requests

    # ── Shutdown ─────────────────────────────────────────────────────
    print("[shutdown] Cerrando aplicación...")


# ---------------------------------------------------------------------------
# Factory — crea y configura la instancia de FastAPI
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """
    Construye la aplicación FastAPI con toda su configuración.

    Retorna la instancia lista para ser usada por uvicorn o en tests.

    Ejemplo en tests:
        from app.interfaces.api.fastapi_app import create_app
        client = TestClient(create_app())
    """
    app = FastAPI(
        title       = "MaCRoM — API de Mediciones de Gas",
        description = (
            "API para gestión, validación y análisis de mediciones de gas.\n\n"
            "Permite registrar mediciones, ejecutar el pipeline de limpieza "
            "y consultar reportes estadísticos."
        ),
        version     = "1.0.0",
        docs_url    = "/docs",
        redoc_url   = "/redoc",
        openapi_url = "/openapi.json",
        debug       = settings.app.debug,
        lifespan    = lifespan,
    )

    _registrar_middleware(app)
    _registrar_routers(app)
    _registrar_manejadores_error(app)

    return app


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

def _registrar_middleware(app: FastAPI) -> None:
    """Configura los middlewares de la aplicación."""

    # CORS — permite requests desde el frontend o herramientas externas
    origins = ["*"] if settings.app.es_desarrollo else [
        "https://tudominio.com",
        "https://app.tudominio.com",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins     = origins,
        allow_credentials = True,
        allow_methods     = ["*"],
        allow_headers     = ["*"],
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

def _registrar_routers(app: FastAPI) -> None:
    """Registra todos los routers de la API."""
    app.include_router(
        mediciones_router,
        prefix = settings.app.api_prefix,
        tags   = ["Mediciones"],
    )


# ---------------------------------------------------------------------------
# Manejadores de error globales
# ---------------------------------------------------------------------------

def _registrar_manejadores_error(app: FastAPI) -> None:
    """Registra handlers para errores no controlados."""

    @app.exception_handler(EnvironmentError)
    async def handler_env_error(request: Request, exc: EnvironmentError):
        return JSONResponse(
            status_code = 500,
            content     = {
                "exitoso" : False,
                "mensaje" : "Error de configuración del servidor.",
                "detalle" : str(exc) if settings.app.debug else "Contacte al administrador.",
            },
        )

    @app.exception_handler(ValueError)
    async def handler_value_error(request: Request, exc: ValueError):
        return JSONResponse(
            status_code = 400,
            content     = {
                "exitoso" : False,
                "mensaje" : "Datos inválidos en la solicitud.",
                "detalle" : str(exc),
            },
        )

    @app.exception_handler(FileNotFoundError)
    async def handler_file_error(request: Request, exc: FileNotFoundError):
        return JSONResponse(
            status_code = 404,
            content     = {
                "exitoso" : False,
                "mensaje" : "Archivo de datos no encontrado.",
                "detalle" : str(exc) if settings.app.debug else "Contacte al administrador.",
            },
        )

    @app.exception_handler(Exception)
    async def handler_generico(request: Request, exc: Exception):
        return JSONResponse(
            status_code = 500,
            content     = {
                "exitoso" : False,
                "mensaje" : "Error interno del servidor.",
                "detalle" : str(exc) if settings.app.debug else "Contacte al administrador.",
            },
        )


# ---------------------------------------------------------------------------
# Instancia de la aplicación — usada por uvicorn
# ---------------------------------------------------------------------------

# uvicorn app.interfaces.api.fastapi_app:app --reload
app = create_app()
