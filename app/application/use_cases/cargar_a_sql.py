"""
application/use_cases/cargar_a_sql.py

Caso de uso: Cargar mediciones limpias a SQL Server.

Responsabilidades:
- Leer las mediciones ya validadas (válidas)
- Delegarle la persistencia al repositorio SQL (via puerto abstracto)
- Reportar el resultado de la carga (cuántas se cargaron, cuántas fallaron)

Reglas Clean Architecture:
- Solo importa del dominio y de otros casos de uso / DTOs de application/
- No importa directamente pyodbc, SQLAlchemy ni nada de infrastructure/
- La implementación concreta del repositorio se inyecta desde afuera (DI)
"""

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.models.medicion import Medicion
from app.domain.repositories.medicion_repository import MedicionRepository


# ---------------------------------------------------------------------------
# DTO de resultado — lo que el caso de uso le devuelve a quien lo invoca
# ---------------------------------------------------------------------------

@dataclass
class ResultadoCarga:
    """
    Resumen del resultado de la operación de carga.

    Attributes
    ----------
    total_recibidas  : Total de mediciones intentadas.
    total_cargadas   : Mediciones insertadas exitosamente en SQL.
    total_fallidas   : Mediciones que fallaron durante la inserción.
    errores          : Detalle de cada fallo { punto_medida: mensaje_error }.
    inicio           : Timestamp de inicio de la carga.
    fin              : Timestamp de fin de la carga.
    """
    total_recibidas : int                  = 0
    total_cargadas  : int                  = 0
    total_fallidas  : int                  = 0
    errores         : dict[str, str]       = field(default_factory=dict)
    inicio          : datetime             = field(default_factory=datetime.utcnow)
    fin             : datetime | None      = None

    @property
    def duracion_segundos(self) -> float | None:
        if self.fin:
            return (self.fin - self.inicio).total_seconds()
        return None

    @property
    def fue_exitosa(self) -> bool:
        """True si al menos una medición se cargó y no hubo fallos."""
        return self.total_cargadas > 0 and self.total_fallidas == 0

    def __str__(self) -> str:
        duracion = f"{self.duracion_segundos:.2f}s" if self.duracion_segundos else "—"
        return (
            f"ResultadoCarga("
            f"cargadas={self.total_cargadas}, "
            f"fallidas={self.total_fallidas}, "
            f"duración={duracion})"
        )


# ---------------------------------------------------------------------------
# Caso de uso
# ---------------------------------------------------------------------------

class CargarASQL:
    """
    Orquesta la carga de mediciones válidas al repositorio SQL.

    Parameters
    ----------
    repositorio : MedicionRepository
        Implementación concreta inyectada desde infrastructure/.
        El caso de uso no sabe si es SQL Server, PostgreSQL o un mock.

    Ejemplo de uso
    --------------
    >>> from app.infrastructure.persistence.sql_repository import SqlMedicionRepository
    >>> from app.infrastructure.config.settings import settings
    >>>
    >>> repo      = SqlMedicionRepository(settings.DB_CONNECTION_STRING)
    >>> caso_uso  = CargarASQL(repositorio=repo)
    >>> resultado = caso_uso.ejecutar(mediciones_validas)
    >>>
    >>> print(resultado)
    >>> if not resultado.fue_exitosa:
    ...     for punto, error in resultado.errores.items():
    ...         print(f"  {punto}: {error}")
    """

    def __init__(self, repositorio: MedicionRepository) -> None:
        self._repo = repositorio

    def ejecutar(self, mediciones: list[Medicion]) -> ResultadoCarga:
        """
        Carga una lista de mediciones válidas al repositorio SQL.

        Estrategia:
        - Intenta un bulk insert (guardar_lote) primero — más eficiente.
        - Si el bulk falla, cae a inserción individual para identificar
          cuál(es) medición(es) específicas están causando el problema.

        Parameters
        ----------
        mediciones : list[Medicion]
            Lista de mediciones ya validadas. Si alguna no es válida,
            igual se intenta insertar — la validación es responsabilidad
            del caso de uso LimpiarMediciones, no de este.

        Returns
        -------
        ResultadoCarga
            Resumen con totales y detalle de errores si los hubo.
        """
        resultado = ResultadoCarga(total_recibidas=len(mediciones))

        if not mediciones:
            resultado.fin = datetime.utcnow()
            return resultado

        # -- Intento 1: bulk insert ----------------------------------------
        try:
            self._repo.guardar_lote(mediciones)
            resultado.total_cargadas = len(mediciones)
            resultado.fin = datetime.utcnow()
            return resultado

        except Exception as bulk_error:
            # El bulk falló — no sabemos cuál medición es la problemática.
            # Caemos a inserción individual para identificar el(los) culpable(s).
            resultado.errores["_bulk"] = (
                f"Bulk insert falló: {bulk_error}. "
                f"Reintentando uno a uno..."
            )

        # -- Intento 2: inserción individual (fallback) ---------------------
        for medicion in mediciones:
            try:
                self._repo.guardar(medicion)
                resultado.total_cargadas += 1

            except Exception as error:
                resultado.total_fallidas += 1
                resultado.errores[medicion.punto_medida] = str(error)

        resultado.fin = datetime.utcnow()
        return resultado
