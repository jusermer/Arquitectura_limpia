"""
domain/repositories/medicion_repository.py

Puerto (port) del dominio: contrato abstracto para persistencia de Mediciones.

Responsabilidades:
- Definir QUÉ operaciones existen (interfaz)
- NO definir CÓMO se implementan (eso es infrastructure/)

Reglas Clean Architecture:
- Solo importa del propio dominio
- Sin pandas, pyodbc, SQLAlchemy, csv ni ninguna librería externa
- infrastructure/persistence/ es quien implementa esta interfaz
"""

from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.models.medicion import Medicion


class MedicionRepository(ABC):
    """
    Interfaz abstracta que deben implementar todos los repositorios
    de Medicion (CSV, SQL Server, mock para tests, etc.).

    Los casos de uso en application/ dependen de esta clase,
    nunca de las implementaciones concretas en infrastructure/.

    Implementaciones esperadas
    --------------------------
    - infrastructure/persistence/csv_repository.py  → CsvMedicionRepository
    - infrastructure/persistence/sql_repository.py  → SqlMedicionRepository
    - tests/.../mock_repository.py                  → MockMedicionRepository
    """

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    @abstractmethod
    def obtener_todas(self) -> list[Medicion]:
        """
        Retorna todas las mediciones disponibles en la fuente de datos.

        Returns
        -------
        list[Medicion]
            Lista de mediciones. Vacía si no hay registros.
        """
        ...

    @abstractmethod
    def obtener_por_punto(self, punto_medida: str) -> list[Medicion]:
        """
        Retorna todas las mediciones de un punto de medida específico.

        Parameters
        ----------
        punto_medida : str
            Identificador del punto (ej: 'EST-BOG-01').

        Returns
        -------
        list[Medicion]
            Lista filtrada. Vacía si no hay registros para ese punto.
        """
        ...

    @abstractmethod
    def obtener_por_rango_fecha(
        self,
        fecha_inicio: datetime,
        fecha_fin: datetime,
    ) -> list[Medicion]:
        """
        Retorna mediciones dentro de un rango de fechas (inclusive).

        Parameters
        ----------
        fecha_inicio : datetime
        fecha_fin    : datetime

        Returns
        -------
        list[Medicion]
        """
        ...

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    @abstractmethod
    def guardar(self, medicion: Medicion) -> None:
        """
        Persiste una única medición en la fuente de datos.

        Parameters
        ----------
        medicion : Medicion
            Entidad a guardar. No modifica el objeto recibido.
        """
        ...

    @abstractmethod
    def guardar_lote(self, mediciones: list[Medicion]) -> None:
        """
        Persiste una lista de mediciones de forma eficiente (bulk insert).

        Preferir este método sobre múltiples llamadas a guardar()
        cuando se procesan lotes grandes.

        Parameters
        ----------
        mediciones : list[Medicion]
            Lista de entidades a guardar.
        """
        ...

    # ------------------------------------------------------------------
    # Eliminación
    # ------------------------------------------------------------------

    @abstractmethod
    def eliminar_por_punto(self, punto_medida: str) -> int:
        """
        Elimina todas las mediciones de un punto de medida.

        Returns
        -------
        int
            Número de registros eliminados.
        """
        ...
