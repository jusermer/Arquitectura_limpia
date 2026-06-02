"""
interfaces/api/schemas/medicion_schema.py

Schemas Pydantic para la capa de API (FastAPI).

Responsabilidades:
- Validar y serializar datos de entrada (request body)
- Estructurar datos de salida (response body)
- Documentar automáticamente la API (OpenAPI / Swagger)
- Convertir entre schemas y DTOs de application/

Reglas Clean Architecture:
- Solo importa de application/dtos/ — NUNCA de domain/ directamente
- La entidad Medicion del dominio NUNCA sale cruda a la API
- Si cambia la API (campos, formatos), solo cambia este archivo

Jerarquía de conversión:
    Request JSON  →  MedicionCreateSchema  →  MedicionCreateDTO  →  Medicion
    Medicion      →  MedicionDTO           →  MedicionSchema      →  Response JSON
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Schema de entrada — POST /mediciones
# ---------------------------------------------------------------------------

class MedicionCreateSchema(BaseModel):
    """
    Valida el body del request al crear una medición via API.

    Pydantic valida tipos, rangos y formatos automáticamente.
    Los errores de validación generan respuestas 422 con detalle.
    """

    punto_medida  : str   = Field(
        ...,
        min_length = 3,
        max_length = 50,
        description = "Identificador del punto de medida (ej: EST-BOG-01)",
        examples    = ["EST-BOG-01"],
    )
    volumen_m3    : float = Field(
        ...,
        gt          = 0,
        description = "Volumen medido en metros cúbicos. Debe ser mayor que cero.",
        examples    = [150.75],
    )
    presion_psi   : float = Field(
        ...,
        gt          = 20,
        lt          = 80,
        description = "Presión en PSI. Rango permitido: 20–80 psi.",
        examples    = [45.2],
    )
    temperatura_c : float = Field(
        ...,
        gt          = -10,
        lt          = 60,
        description = "Temperatura en grados Celsius. Rango: -10 a 60 °C.",
        examples    = [22.5],
    )
    calidad_gas   : float = Field(
        ...,
        ge          = 0.85,
        le          = 1.0,
        description = "Índice de calidad del gas. Rango: 0.85 a 1.00.",
        examples    = [0.95],
    )
    operador      : str   = Field(
        ...,
        min_length  = 2,
        max_length  = 100,
        description = "Nombre del operador responsable de la medición.",
        examples    = ["Carlos Mejía"],
    )
    fecha         : Optional[datetime] = Field(
        default     = None,
        description = "Fecha y hora de la medición (ISO 8601). Si se omite, se usa la hora actual UTC.",
        examples    = ["2024-03-15T08:30:00"],
    )

    # ------------------------------------------------------------------
    # Validadores de campo
    # ------------------------------------------------------------------

    @field_validator("punto_medida")
    @classmethod
    def normalizar_punto(cls, v: str) -> str:
        """Normaliza a mayúsculas y elimina espacios."""
        return v.strip().upper()

    @field_validator("operador")
    @classmethod
    def normalizar_operador(cls, v: str) -> str:
        return v.strip()

    @field_validator("volumen_m3", "presion_psi", "temperatura_c", "calidad_gas")
    @classmethod
    def redondear_floats(cls, v: float) -> float:
        return round(v, 4)

    @model_validator(mode="after")
    def asignar_fecha_si_none(self) -> "MedicionCreateSchema":
        """Si no se envió fecha, asigna la hora actual UTC."""
        if self.fecha is None:
            object.__setattr__(self, "fecha", datetime.utcnow())
        return self

    # ------------------------------------------------------------------
    # Conversión a DTO de application/
    # ------------------------------------------------------------------

    def a_dto(self):
        """
        Convierte el schema a MedicionCreateDTO para pasarlo al caso de uso.

        Import local para evitar dependencia circular en el módulo.
        """
        from app.application.dtos.medicion_dto import MedicionCreateDTO
        return MedicionCreateDTO(
            punto_medida  = self.punto_medida,
            volumen_m3    = self.volumen_m3,
            presion_psi   = self.presion_psi,
            temperatura_c = self.temperatura_c,
            calidad_gas   = self.calidad_gas,
            operador      = self.operador,
            fecha         = self.fecha,
        )

    model_config = {
        "json_schema_extra": {
            "example": {
                "punto_medida"  : "EST-BOG-01",
                "volumen_m3"    : 150.75,
                "presion_psi"   : 45.2,
                "temperatura_c" : 22.5,
                "calidad_gas"   : 0.95,
                "operador"      : "Carlos Mejía",
                "fecha"         : "2024-03-15T08:30:00",
            }
        }
    }


# ---------------------------------------------------------------------------
# Schema de salida — GET /mediciones (response)
# ---------------------------------------------------------------------------

class MedicionSchema(BaseModel):
    """
    Estructura la respuesta JSON de una medición.

    Se construye desde MedicionDTO, nunca desde la entidad de dominio.
    """

    fecha           : str
    punto_medida    : str
    volumen_m3      : float
    presion_psi     : float
    temperatura_c   : float
    calidad_gas     : float
    operador        : str
    es_valida       : bool
    errores         : list[str]

    # ------------------------------------------------------------------
    # Factory method: MedicionDTO → MedicionSchema
    # ------------------------------------------------------------------

    @classmethod
    def desde_dto(cls, dto) -> "MedicionSchema":
        """
        Construye el schema de respuesta desde un MedicionDTO.

        Parameters
        ----------
        dto : MedicionDTO
            DTO de la capa application/.
        """
        return cls(
            fecha         = dto.fecha,
            punto_medida  = dto.punto_medida,
            volumen_m3    = dto.volumen_m3,
            presion_psi   = dto.presion_psi,
            temperatura_c = dto.temperatura_c,
            calidad_gas   = dto.calidad_gas,
            operador      = dto.operador,
            es_valida     = dto.es_valida,
            errores       = list(dto.errores),
        )

    @classmethod
    def lista_desde_dtos(cls, dtos: list) -> list["MedicionSchema"]:
        return [cls.desde_dto(dto) for dto in dtos]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Schemas de respuesta envueltos — estructura estándar de la API
# ---------------------------------------------------------------------------

class RespuestaBase(BaseModel):
    """Estructura base para todas las respuestas de la API."""
    exitoso : bool
    mensaje : str


class RespuestaMedicion(RespuestaBase):
    """Respuesta con una sola medición."""
    data : Optional[MedicionSchema] = None


class RespuestaListaMediciones(RespuestaBase):
    """Respuesta con lista de mediciones y metadatos de paginación."""
    data          : list[MedicionSchema] = Field(default_factory=list)
    total         : int = 0
    total_validas : int = 0
    total_invalidas: int = 0


class RespuestaPipeline(RespuestaBase):
    """
    Respuesta del endpoint que dispara el pipeline completo
    POST /mediciones/procesar
    """
    total_leidas    : int = 0
    total_validas   : int = 0
    total_invalidas : int = 0
    total_cargadas  : int = 0
    duracion_segundos: Optional[float] = None
    errores_pipeline : list[str] = Field(default_factory=list)
