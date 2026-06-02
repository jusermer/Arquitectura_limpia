"""
application/dtos/medicion_dto.py

DTOs (Data Transfer Objects) de la capa application.

Responsabilidades:
- Transportar datos entre capas sin exponer la entidad de dominio
- Desacoplar la representación interna (Medicion) de la externa (API, CLI, CSV)
- Proveer conversores explícitos desde/hacia la entidad de dominio

Reglas Clean Architecture:
- Solo importa del dominio (modelos) y tipos nativos de Python
- Sin FastAPI, pydantic, pandas ni nada de infrastructure/ o interfaces/
- Los schemas de Pydantic para la API viven en interfaces/api/schemas/
  y se construyen desde estos DTOs, no desde la entidad directamente

Flujo de datos
--------------
CSV/SQL  →  Medicion (domain)  →  MedicionDTO  →  API response / reporte
API request  →  MedicionCreateDTO  →  Medicion (domain)  →  persistencia
"""

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.models.medicion import Medicion


# ---------------------------------------------------------------------------
# DTO de lectura — para mostrar o exportar una medición existente
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MedicionDTO:
    """
    Representación inmutable de una Medicion para transferencia entre capas.

    frozen=True:
    - Garantiza que nadie modifica el DTO después de crearlo
    - Hace el objeto hashable (útil para sets y dict keys)
    - Comunica intención: este objeto es solo para leer/transferir

    Se usa cuando:
    - La API retorna una o varias mediciones (response)
    - El CLI imprime el resultado de un proceso
    - El exportador CSV serializa mediciones válidas
    - Los tests verifican salidas sin tocar la entidad de dominio
    """

    fecha           : str    # ISO 8601: "2024-03-15T08:30:00"
    punto_medida    : str
    volumen_m3      : float
    presion_psi     : float
    temperatura_c   : float
    calidad_gas     : float
    operador        : str
    es_valida       : bool
    errores         : tuple[str, ...]  # tuple en lugar de list → inmutable

    # ------------------------------------------------------------------
    # Factory method: Medicion → MedicionDTO
    # ------------------------------------------------------------------

    @classmethod
    def desde_entidad(cls, medicion: Medicion) -> "MedicionDTO":
        """
        Construye un MedicionDTO a partir de una entidad de dominio.

        Parameters
        ----------
        medicion : Medicion
            Entidad del dominio, con o sin errores.

        Returns
        -------
        MedicionDTO
            DTO inmutable listo para transferir.

        Ejemplo
        -------
        >>> dto = MedicionDTO.desde_entidad(m)
        >>> print(dto.fecha)
        '2024-03-15T08:30:00'
        """
        return cls(
            fecha         = medicion.fecha.isoformat(),
            punto_medida  = medicion.punto_medida,
            volumen_m3    = medicion.volumen_m3,
            presion_psi   = medicion.presion_psi,
            temperatura_c = medicion.temperatura_c,
            calidad_gas   = medicion.calidad_gas,
            operador      = medicion.operador,
            es_valida     = not medicion.tiene_errores(),
            errores       = tuple(medicion.errores),
        )

    @classmethod
    def lista_desde_entidades(cls, mediciones: list[Medicion]) -> list["MedicionDTO"]:
        """
        Convierte una lista de entidades a una lista de DTOs.

        Ejemplo
        -------
        >>> dtos = MedicionDTO.lista_desde_entidades(validas)
        """
        return [cls.desde_entidad(m) for m in mediciones]

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def a_dict(self) -> dict:
        """
        Convierte el DTO a diccionario plano.
        Útil para serializar a JSON, CSV o logs.
        """
        return {
            "fecha"         : self.fecha,
            "punto_medida"  : self.punto_medida,
            "volumen_m3"    : self.volumen_m3,
            "presion_psi"   : self.presion_psi,
            "temperatura_c" : self.temperatura_c,
            "calidad_gas"   : self.calidad_gas,
            "operador"      : self.operador,
            "es_valida"     : self.es_valida,
            "errores"       : " | ".join(self.errores) if self.errores else "",
        }

    def __str__(self) -> str:
        estado = "VÁLIDA" if self.es_valida else f"INVÁLIDA ({len(self.errores)} errores)"
        return (
            f"MedicionDTO("
            f"fecha={self.fecha}, "
            f"punto='{self.punto_medida}', "
            f"volumen={self.volumen_m3} m³, "
            f"estado={estado})"
        )


# ---------------------------------------------------------------------------
# DTO de creación — para recibir datos desde afuera (API, CLI)
# ---------------------------------------------------------------------------

@dataclass
class MedicionCreateDTO:
    """
    DTO para crear una nueva medición a partir de datos externos.

    No es frozen porque puede necesitar normalización antes de
    convertirse en una entidad de dominio.

    Se usa cuando:
    - La API recibe un POST con datos de una nueva medición
    - La CLI recibe argumentos para registrar una medición manual
    - Un test construye una medición sin pasar por el CSV

    La validación de reglas de negocio (rangos, fechas) NO ocurre aquí.
    Este DTO solo valida que los tipos sean correctos antes de crear
    la entidad. Las reglas de negocio son responsabilidad del dominio.
    """

    punto_medida    : str
    volumen_m3      : float
    presion_psi     : float
    temperatura_c   : float
    calidad_gas     : float
    operador        : str
    fecha           : datetime = field(default_factory=datetime.utcnow)

    # ------------------------------------------------------------------
    # Normalización básica de tipos
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        """
        Normaliza los datos al momento de la creación.
        Solo limpieza de tipos, nunca lógica de negocio.
        """
        self.punto_medida = self.punto_medida.strip().upper()
        self.operador     = self.operador.strip()
        self.volumen_m3   = round(float(self.volumen_m3), 4)
        self.presion_psi  = round(float(self.presion_psi), 4)
        self.temperatura_c = round(float(self.temperatura_c), 4)
        self.calidad_gas  = round(float(self.calidad_gas), 4)

    # ------------------------------------------------------------------
    # Factory method: MedicionCreateDTO → Medicion (entidad de dominio)
    # ------------------------------------------------------------------

    def a_entidad(self) -> Medicion:
        """
        Construye una entidad Medicion a partir de este DTO.

        La entidad sale en estado limpio (sin errores).
        Las reglas de negocio se aplican después con reglas_validacion.

        Returns
        -------
        Medicion
            Entidad de dominio lista para ser validada.

        Ejemplo
        -------
        >>> create_dto = MedicionCreateDTO(
        ...     punto_medida  = "est-bog-01",
        ...     volumen_m3    = 150.5,
        ...     presion_psi   = 45.0,
        ...     temperatura_c = 22.0,
        ...     calidad_gas   = 0.95,
        ...     operador      = "Carlos M.",
        ... )
        >>> medicion = create_dto.a_entidad()
        >>> print(medicion.punto_medida)  # "EST-BOG-01" (normalizado)
        """
        return Medicion(
            fecha         = self.fecha,
            punto_medida  = self.punto_medida,
            volumen_m3    = self.volumen_m3,
            presion_psi   = self.presion_psi,
            temperatura_c = self.temperatura_c,
            calidad_gas   = self.calidad_gas,
            operador      = self.operador,
        )
