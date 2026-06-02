"""
application/use_cases/limpiar_mediciones.py

Caso de uso principal: Orquesta el pipeline completo de limpieza.

Flujo:
  1. Leer todas las mediciones crudas desde el repositorio fuente
  2. Validar cada medición con las reglas de dominio
  3. Separar en válidas e inválidas
  4. Persistir válidas en el repositorio destino (SQL)
  5. Persistir inválidas en el repositorio de rechazos (CSV)
  6. Generar y retornar el resumen del proceso

Reglas Clean Architecture:
- Orquesta, no implementa — toda la lógica real vive en domain/ o en los
  otros casos de uso (CargarASQL, GenerarResumen)
- Depende solo de abstracciones (MedicionRepository), nunca de concretos
- Sin pandas, pyodbc, csv ni ninguna librería de infraestructura
- Los repositorios y casos de uso se inyectan desde afuera (DI)
"""

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.models.medicion import Medicion
from app.domain.repositories.medicion_repository import MedicionRepository
from app.domain.services.reglas_validacion import validar_lote

from app.application.use_cases.cargar_a_sql import CargarASQL, ResultadoCarga
from app.application.use_cases.generar_resumen import GenerarResumen, ResumenGeneral


# ---------------------------------------------------------------------------
# DTO de resultado del pipeline completo
# ---------------------------------------------------------------------------

@dataclass
class ResultadoPipeline:
    """
    Resultado consolidado de todo el proceso de limpieza.

    Attributes
    ----------
    total_leidas      : Mediciones leídas desde la fuente.
    total_validas     : Mediciones que pasaron todas las reglas.
    total_invalidas   : Mediciones rechazadas por alguna regla.
    carga_sql         : Resultado detallado de la carga a SQL Server.
    resumen           : Estadísticas completas del lote procesado.
    inicio            : Timestamp de inicio del pipeline.
    fin               : Timestamp de fin del pipeline.
    errores_pipeline  : Errores críticos que interrumpieron el proceso.
    """
    total_leidas      : int                    = 0
    total_validas     : int                    = 0
    total_invalidas   : int                    = 0
    carga_sql         : ResultadoCarga | None  = None
    resumen           : ResumenGeneral | None  = None
    inicio            : datetime               = field(default_factory=datetime.utcnow)
    fin               : datetime | None        = None
    errores_pipeline  : list[str]              = field(default_factory=list)

    @property
    def duracion_segundos(self) -> float | None:
        if self.fin:
            return round((self.fin - self.inicio).total_seconds(), 2)
        return None

    @property
    def fue_exitoso(self) -> bool:
        """True si no hubo errores críticos y se cargó al menos una medición."""
        return (
            not self.errores_pipeline
            and self.carga_sql is not None
            and self.carga_sql.fue_exitosa
        )

    @property
    def tasa_validez(self) -> float:
        if self.total_leidas == 0:
            return 0.0
        return round(self.total_validas / self.total_leidas * 100, 2)

    def __str__(self) -> str:
        duracion = f"{self.duracion_segundos}s" if self.duracion_segundos else "—"
        return (
            f"ResultadoPipeline("
            f"leídas={self.total_leidas}, "
            f"válidas={self.total_validas} ({self.tasa_validez}%), "
            f"inválidas={self.total_invalidas}, "
            f"duración={duracion}, "
            f"exitoso={self.fue_exitoso})"
        )


# ---------------------------------------------------------------------------
# Caso de uso
# ---------------------------------------------------------------------------

class LimpiarMediciones:
    """
    Orquesta el pipeline completo de limpieza y carga de mediciones.

    Parameters
    ----------
    repo_fuente   : MedicionRepository
        Repositorio de donde se leen las mediciones crudas (CSV).
    repo_sql      : MedicionRepository
        Repositorio donde se persisten las mediciones válidas (SQL Server).
    repo_rechazos : MedicionRepository
        Repositorio donde se persisten las mediciones inválidas (CSV rechazos).

    Ejemplo de uso
    --------------
    >>> caso_uso = LimpiarMediciones(
    ...     repo_fuente   = CsvMedicionRepository("data/raw/mediciones_gas.csv"),
    ...     repo_sql      = SqlMedicionRepository(settings.DB_CONNECTION_STRING),
    ...     repo_rechazos = CsvMedicionRepository("data/processed/mediciones_invalidas.csv"),
    ... )
    >>> resultado = caso_uso.ejecutar()
    >>> print(resultado)
    >>> if not resultado.fue_exitoso:
    ...     for error in resultado.errores_pipeline:
    ...         print(f"  ERROR: {error}")
    """

    def __init__(
        self,
        repo_fuente   : MedicionRepository,
        repo_sql      : MedicionRepository,
        repo_rechazos : MedicionRepository,
    ) -> None:
        self._repo_fuente   = repo_fuente
        self._repo_sql      = repo_sql
        self._repo_rechazos = repo_rechazos

    def ejecutar(self) -> ResultadoPipeline:
        """
        Ejecuta el pipeline completo.

        Pasos
        -----
        1. Leer mediciones crudas
        2. Validar y separar
        3. Persistir inválidas en repo de rechazos
        4. Cargar válidas a SQL
        5. Generar resumen estadístico

        Returns
        -------
        ResultadoPipeline
            Resultado consolidado. Nunca lanza excepciones al caller —
            los errores se acumulan en resultado.errores_pipeline.
        """
        resultado = ResultadoPipeline()

        # ------------------------------------------------------------------
        # Paso 1: Leer mediciones crudas
        # ------------------------------------------------------------------
        mediciones = self._leer_mediciones(resultado)
        if not mediciones:
            resultado.fin = datetime.utcnow()
            return resultado

        resultado.total_leidas = len(mediciones)

        # ------------------------------------------------------------------
        # Paso 2: Validar y separar en válidas e inválidas
        # ------------------------------------------------------------------
        validas, invalidas = validar_lote(mediciones)
        resultado.total_validas   = len(validas)
        resultado.total_invalidas = len(invalidas)

        # ------------------------------------------------------------------
        # Paso 3: Persistir inválidas en repositorio de rechazos
        # ------------------------------------------------------------------
        self._persistir_rechazos(invalidas, resultado)

        # ------------------------------------------------------------------
        # Paso 4: Cargar válidas a SQL Server
        # ------------------------------------------------------------------
        self._cargar_a_sql(validas, resultado)

        # ------------------------------------------------------------------
        # Paso 5: Generar resumen estadístico
        # ------------------------------------------------------------------
        self._generar_resumen(validas, invalidas, resultado)

        resultado.fin = datetime.utcnow()
        return resultado

    # ------------------------------------------------------------------
    # Pasos privados — cada uno aísla su propio try/except
    # para que un fallo no detenga los pasos siguientes
    # ------------------------------------------------------------------

    def _leer_mediciones(self, resultado: ResultadoPipeline) -> list[Medicion]:
        try:
            mediciones = self._repo_fuente.obtener_todas()
            if not mediciones:
                resultado.errores_pipeline.append(
                    "La fuente de datos no contiene mediciones."
                )
            return mediciones
        except Exception as e:
            resultado.errores_pipeline.append(
                f"Error al leer mediciones desde la fuente: {e}"
            )
            return []

    def _persistir_rechazos(
        self,
        invalidas : list[Medicion],
        resultado : ResultadoPipeline,
    ) -> None:
        if not invalidas:
            return
        try:
            self._repo_rechazos.guardar_lote(invalidas)
        except Exception as e:
            resultado.errores_pipeline.append(
                f"Error al persistir mediciones inválidas: {e}"
            )

    def _cargar_a_sql(
        self,
        validas   : list[Medicion],
        resultado : ResultadoPipeline,
    ) -> None:
        if not validas:
            resultado.errores_pipeline.append(
                "No hay mediciones válidas para cargar a SQL."
            )
            return
        try:
            caso_uso_sql      = CargarASQL(repositorio=self._repo_sql)
            resultado.carga_sql = caso_uso_sql.ejecutar(validas)
        except Exception as e:
            resultado.errores_pipeline.append(
                f"Error inesperado durante la carga a SQL: {e}"
            )

    def _generar_resumen(
        self,
        validas   : list[Medicion],
        invalidas : list[Medicion],
        resultado : ResultadoPipeline,
    ) -> None:
        try:
            caso_uso_resumen = GenerarResumen(repositorio=self._repo_fuente)
            resultado.resumen = caso_uso_resumen.ejecutar(validas, invalidas)
        except Exception as e:
            resultado.errores_pipeline.append(
                f"Error al generar el resumen estadístico: {e}"
            )
