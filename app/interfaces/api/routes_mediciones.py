"""
interfaces/api/routes_mediciones.py

Endpoints REST para el recurso Mediciones.

Responsabilidades:
- Definir las rutas HTTP (GET, POST)
- Inyectar dependencias (repositorios, casos de uso)
- Convertir schemas de entrada a DTOs y DTOs a schemas de salida
- Retornar respuestas HTTP con el código de estado correcto

Reglas Clean Architecture:
- No contiene lógica de negocio — solo orquesta
- Depende de schemas (interfaces/) y casos de uso (application/)
- Los repositorios se inyectan via FastAPI Depends()

Endpoints:
    GET    /mediciones                → lista todas las mediciones
    GET    /mediciones/{punto_medida} → filtra por punto
    POST   /mediciones                → registra una nueva medición
    POST   /mediciones/procesar       → dispara el pipeline completo
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.infrastructure.config.settings import settings
from app.infrastructure.persistence.csv_repository import CsvMedicionRepository
from app.infrastructure.persistence.sql_repository import SqlMedicionRepository
from app.domain.repositories.medicion_repository import MedicionRepository
from app.domain.services.reglas_validacion import validar_medicion
from app.application.use_cases.limpiar_mediciones import LimpiarMediciones
from app.application.dtos.medicion_dto import MedicionDTO

from app.interfaces.api.schemas.medicion_schema import (
    MedicionCreateSchema,
    MedicionSchema,
    RespuestaMedicion,
    RespuestaListaMediciones,
    RespuestaPipeline,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependencias — inyectadas por FastAPI en cada request
# ---------------------------------------------------------------------------

def get_repo_csv() -> MedicionRepository:
    """Repositorio CSV de mediciones crudas (fuente de lectura)."""
    return CsvMedicionRepository(settings.paths.raw_mediciones)


def get_repo_sql() -> MedicionRepository:
    """Repositorio SQL Server (destino de mediciones válidas)."""
    return SqlMedicionRepository(settings.db.connection_string)


def get_repo_rechazos() -> MedicionRepository:
    """Repositorio CSV de mediciones inválidas (rechazos)."""
    return CsvMedicionRepository(settings.paths.mediciones_invalidas)


def get_repo_limpias() -> MedicionRepository:
    """Repositorio CSV de mediciones limpias procesadas."""
    return CsvMedicionRepository(settings.paths.mediciones_limpias)


# ---------------------------------------------------------------------------
# GET /mediciones
# ---------------------------------------------------------------------------

@router.get(
    "/mediciones",
    response_model = RespuestaListaMediciones,
    summary        = "Obtener todas las mediciones",
    description    = "Retorna todas las mediciones del archivo CSV fuente.",
    status_code    = status.HTTP_200_OK,
)
def obtener_mediciones(
    repo: MedicionRepository = Depends(get_repo_csv),
) -> RespuestaListaMediciones:
    mediciones = repo.obtener_todas()

    dtos    = MedicionDTO.lista_desde_entidades(mediciones)
    schemas = MedicionSchema.lista_desde_dtos(dtos)

    validas   = [s for s in schemas if s.es_valida]
    invalidas = [s for s in schemas if not s.es_valida]

    return RespuestaListaMediciones(
        exitoso          = True,
        mensaje          = f"{len(schemas)} mediciones encontradas.",
        data             = schemas,
        total            = len(schemas),
        total_validas    = len(validas),
        total_invalidas  = len(invalidas),
    )


# ---------------------------------------------------------------------------
# GET /mediciones/{punto_medida}
# ---------------------------------------------------------------------------

@router.get(
    "/mediciones/{punto_medida}",
    response_model = RespuestaListaMediciones,
    summary        = "Obtener mediciones por punto de medida",
    status_code    = status.HTTP_200_OK,
)
def obtener_por_punto(
    punto_medida : str,
    repo         : MedicionRepository = Depends(get_repo_csv),
) -> RespuestaListaMediciones:
    mediciones = repo.obtener_por_punto(punto_medida)

    if not mediciones:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail      = f"No se encontraron mediciones para el punto '{punto_medida}'.",
        )

    dtos    = MedicionDTO.lista_desde_entidades(mediciones)
    schemas = MedicionSchema.lista_desde_dtos(dtos)

    return RespuestaListaMediciones(
        exitoso         = True,
        mensaje         = f"{len(schemas)} mediciones para '{punto_medida.upper()}'.",
        data            = schemas,
        total           = len(schemas),
        total_validas   = len([s for s in schemas if s.es_valida]),
        total_invalidas = len([s for s in schemas if not s.es_valida]),
    )


# ---------------------------------------------------------------------------
# POST /mediciones
# ---------------------------------------------------------------------------

@router.post(
    "/mediciones",
    response_model = RespuestaMedicion,
    summary        = "Registrar una nueva medición",
    description    = (
        "Recibe una medición, aplica las reglas de negocio del dominio "
        "y la persiste en SQL Server si es válida, o en el CSV de rechazos si no."
    ),
    status_code    = status.HTTP_201_CREATED,
)
def registrar_medicion(
    body          : MedicionCreateSchema,
    repo_sql      : MedicionRepository = Depends(get_repo_sql),
    repo_rechazos : MedicionRepository = Depends(get_repo_rechazos),
) -> RespuestaMedicion:
    # 1. Schema → DTO → Entidad
    medicion = body.a_dto().a_entidad()

    # 2. Validar con reglas de dominio
    es_valida = validar_medicion(medicion)

    # 3. Persistir según resultado
    if es_valida:
        repo_sql.guardar(medicion)
        mensaje = "Medición registrada exitosamente en SQL Server."
    else:
        repo_rechazos.guardar(medicion)
        mensaje = f"Medición inválida guardada en rechazos. Errores: {medicion.errores}"

    # 4. Construir respuesta
    dto    = MedicionDTO.desde_entidad(medicion)
    schema = MedicionSchema.desde_dto(dto)

    return RespuestaMedicion(
        exitoso = es_valida,
        mensaje = mensaje,
        data    = schema,
    )


# ---------------------------------------------------------------------------
# POST /mediciones/procesar
# ---------------------------------------------------------------------------

@router.post(
    "/mediciones/procesar",
    response_model = RespuestaPipeline,
    summary        = "Ejecutar pipeline completo de limpieza y carga",
    description    = (
        "Lee el CSV fuente, valida todas las mediciones, carga las válidas "
        "a SQL Server y guarda las inválidas en el CSV de rechazos."
    ),
    status_code    = status.HTTP_200_OK,
)
def ejecutar_pipeline(
    repo_fuente   : MedicionRepository = Depends(get_repo_csv),
    repo_sql      : MedicionRepository = Depends(get_repo_sql),
    repo_rechazos : MedicionRepository = Depends(get_repo_rechazos),
) -> RespuestaPipeline:
    caso_uso  = LimpiarMediciones(
        repo_fuente   = repo_fuente,
        repo_sql      = repo_sql,
        repo_rechazos = repo_rechazos,
    )

    resultado = caso_uso.ejecutar()

    return RespuestaPipeline(
        exitoso           = resultado.fue_exitoso,
        mensaje           = (
            "Pipeline ejecutado exitosamente."
            if resultado.fue_exitoso
            else "Pipeline finalizado con errores."
        ),
        total_leidas      = resultado.total_leidas,
        total_validas     = resultado.total_validas,
        total_invalidas   = resultado.total_invalidas,
        total_cargadas    = resultado.carga_sql.total_cargadas if resultado.carga_sql else 0,
        duracion_segundos = resultado.duracion_segundos,
        errores_pipeline  = resultado.errores_pipeline,
    )
