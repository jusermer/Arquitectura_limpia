"""
application/use_cases/generar_resumen.py

Caso de uso: Generar resumen estadístico de las mediciones procesadas.

Responsabilidades:
- Calcular estadísticas agregadas sobre mediciones válidas e inválidas
- Agrupar por punto de medida y por operador
- Devolver un DTO con el resumen listo para exportar o mostrar

Reglas Clean Architecture:
- Solo importa del dominio y tipos nativos de Python
- Sin pandas — los cálculos se hacen con stdlib (statistics, collections)
- Sin lógica de persistencia ni de presentación
- El repositorio se inyecta desde afuera
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.models.medicion import Medicion
from app.domain.repositories.medicion_repository import MedicionRepository


# ---------------------------------------------------------------------------
# DTOs de resultado
# ---------------------------------------------------------------------------

@dataclass
class ResumenPunto:
    """Estadísticas agregadas por punto de medida."""
    punto_medida      : str
    total_mediciones  : int
    volumen_total_m3  : float
    volumen_promedio  : float
    volumen_max       : float
    volumen_min       : float
    presion_promedio  : float
    temperatura_prom  : float
    calidad_promedio  : float
    total_invalidas   : int

    @property
    def tasa_invalidez(self) -> float:
        """Porcentaje de mediciones inválidas sobre el total."""
        if self.total_mediciones == 0:
            return 0.0
        return round(self.total_invalidas / self.total_mediciones * 100, 2)

    def __str__(self) -> str:
        return (
            f"[{self.punto_medida}] "
            f"total={self.total_mediciones} | "
            f"vol_total={self.volumen_total_m3:.2f} m³ | "
            f"invalidas={self.total_invalidas} ({self.tasa_invalidez}%)"
        )


@dataclass
class ResumenOperador:
    """Estadísticas agregadas por operador."""
    operador         : str
    total_mediciones : int
    total_invalidas  : int
    puntos_operados  : list[str] = field(default_factory=list)

    @property
    def tasa_invalidez(self) -> float:
        if self.total_mediciones == 0:
            return 0.0
        return round(self.total_invalidas / self.total_mediciones * 100, 2)


@dataclass
class ResumenGeneral:
    """
    DTO principal que devuelve el caso de uso.

    Contiene el resumen global, por punto de medida y por operador.
    """
    # Totales globales
    total_mediciones    : int
    total_validas       : int
    total_invalidas     : int
    fecha_generacion    : datetime

    # Rangos globales
    fecha_primera       : datetime | None
    fecha_ultima        : datetime | None

    # Promedios globales
    volumen_promedio    : float
    presion_promedio    : float
    temperatura_prom    : float
    calidad_promedio    : float

    # Desglose
    por_punto           : list[ResumenPunto]    = field(default_factory=list)
    por_operador        : list[ResumenOperador] = field(default_factory=list)

    # Top problemáticos
    punto_mas_invalidos : str | None = None
    operador_mas_fallos : str | None = None

    @property
    def tasa_validez(self) -> float:
        if self.total_mediciones == 0:
            return 0.0
        return round(self.total_validas / self.total_mediciones * 100, 2)

    @property
    def tasa_invalidez(self) -> float:
        return round(100 - self.tasa_validez, 2)

    def __str__(self) -> str:
        return (
            f"ResumenGeneral("
            f"total={self.total_mediciones}, "
            f"válidas={self.total_validas} ({self.tasa_validez}%), "
            f"inválidas={self.total_invalidas} ({self.tasa_invalidez}%), "
            f"generado={self.fecha_generacion.strftime('%Y-%m-%d %H:%M:%S')})"
        )


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _promedio(valores: list[float]) -> float:
    """Retorna el promedio o 0.0 si la lista está vacía."""
    return round(statistics.mean(valores), 4) if valores else 0.0


def _agrupar_por_punto(
    validas: list[Medicion],
    invalidas: list[Medicion],
) -> list[ResumenPunto]:
    """Construye un ResumenPunto por cada punto de medida único."""

    # Acumular datos de válidas
    datos: dict[str, dict] = defaultdict(lambda: {
        "volumenes"     : [],
        "presiones"     : [],
        "temperaturas"  : [],
        "calidades"     : [],
        "total"         : 0,
        "invalidas"     : 0,
    })

    for m in validas:
        d = datos[m.punto_medida]
        d["volumenes"].append(m.volumen_m3)
        d["presiones"].append(m.presion_psi)
        d["temperaturas"].append(m.temperatura_c)
        d["calidades"].append(m.calidad_gas)
        d["total"] += 1

    # Contar inválidas por punto
    for m in invalidas:
        datos[m.punto_medida]["invalidas"] += 1
        datos[m.punto_medida]["total"] += 1

    resumenes = []
    for punto, d in datos.items():
        vols = d["volumenes"]
        resumenes.append(ResumenPunto(
            punto_medida     = punto,
            total_mediciones = d["total"],
            volumen_total_m3 = round(sum(vols), 4) if vols else 0.0,
            volumen_promedio = _promedio(vols),
            volumen_max      = max(vols) if vols else 0.0,
            volumen_min      = min(vols) if vols else 0.0,
            presion_promedio = _promedio(d["presiones"]),
            temperatura_prom = _promedio(d["temperaturas"]),
            calidad_promedio = _promedio(d["calidades"]),
            total_invalidas  = d["invalidas"],
        ))

    return sorted(resumenes, key=lambda r: r.total_invalidas, reverse=True)


def _agrupar_por_operador(
    validas: list[Medicion],
    invalidas: list[Medicion],
) -> list[ResumenOperador]:
    """Construye un ResumenOperador por cada operador único."""

    datos: dict[str, dict] = defaultdict(lambda: {
        "total"    : 0,
        "invalidas": 0,
        "puntos"   : set(),
    })

    for m in validas:
        datos[m.operador]["total"] += 1
        datos[m.operador]["puntos"].add(m.punto_medida)

    for m in invalidas:
        datos[m.operador]["invalidas"] += 1
        datos[m.operador]["total"] += 1
        datos[m.operador]["puntos"].add(m.punto_medida)

    return [
        ResumenOperador(
            operador         = op,
            total_mediciones = d["total"],
            total_invalidas  = d["invalidas"],
            puntos_operados  = sorted(d["puntos"]),
        )
        for op, d in datos.items()
    ]


# ---------------------------------------------------------------------------
# Caso de uso
# ---------------------------------------------------------------------------

class GenerarResumen:
    """
    Genera un resumen estadístico de las mediciones procesadas.

    Parameters
    ----------
    repositorio : MedicionRepository
        Fuente de datos. El caso de uso no sabe si es CSV, SQL o mock.

    Ejemplo de uso
    --------------
    >>> caso_uso = GenerarResumen(repositorio=repo)
    >>> resumen  = caso_uso.ejecutar(validas, invalidas)
    >>> print(resumen)
    >>> for punto in resumen.por_punto:
    ...     print(punto)
    """

    def __init__(self, repositorio: MedicionRepository) -> None:
        self._repo = repositorio

    def ejecutar(
        self,
        validas   : list[Medicion],
        invalidas : list[Medicion],
    ) -> ResumenGeneral:
        """
        Calcula el resumen estadístico a partir de dos listas de mediciones.

        Parameters
        ----------
        validas   : list[Medicion]  Mediciones que pasaron la validación.
        invalidas : list[Medicion]  Mediciones que fallaron la validación.

        Returns
        -------
        ResumenGeneral
            DTO con estadísticas globales, por punto y por operador.
        """
        todas = validas + invalidas

        if not todas:
            return ResumenGeneral(
                total_mediciones = 0,
                total_validas    = 0,
                total_invalidas  = 0,
                fecha_generacion = datetime.utcnow(),
                fecha_primera    = None,
                fecha_ultima     = None,
                volumen_promedio = 0.0,
                presion_promedio = 0.0,
                temperatura_prom = 0.0,
                calidad_promedio = 0.0,
            )

        # Estadísticas globales (solo sobre válidas para no distorsionar)
        fechas = [m.fecha for m in todas]
        por_punto    = _agrupar_por_punto(validas, invalidas)
        por_operador = _agrupar_por_operador(validas, invalidas)

        # Top problemáticos
        punto_top = por_punto[0].punto_medida if por_punto else None
        op_top = max(
            por_operador,
            key=lambda o: o.total_invalidas,
            default=None,
        )

        return ResumenGeneral(
            total_mediciones    = len(todas),
            total_validas       = len(validas),
            total_invalidas     = len(invalidas),
            fecha_generacion    = datetime.utcnow(),
            fecha_primera       = min(fechas),
            fecha_ultima        = max(fechas),
            volumen_promedio    = _promedio([m.volumen_m3    for m in validas]),
            presion_promedio    = _promedio([m.presion_psi   for m in validas]),
            temperatura_prom    = _promedio([m.temperatura_c for m in validas]),
            calidad_promedio    = _promedio([m.calidad_gas   for m in validas]),
            por_punto           = por_punto,
            por_operador        = por_operador,
            punto_mas_invalidos = punto_top,
            operador_mas_fallos = op_top.operador if op_top else None,
        )
