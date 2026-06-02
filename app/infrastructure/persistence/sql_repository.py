"""
infrastructure/persistence/sql_repository.py

Implementación concreta del puerto MedicionRepository para SQL Server.

Responsabilidades:
- Conectarse a SQL Server via pyodbc
- Ejecutar queries CRUD sobre la tabla de mediciones
- Mapear entre filas SQL y entidades de dominio (Medicion)
- Gestionar conexiones y transacciones de forma segura

Reglas Clean Architecture:
- Implementa MedicionRepository (puerto del dominio)
- El dominio NO conoce este archivo
- Toda la lógica de SQL (queries, conexión, cursores) queda aquí
- Si se cambia de SQL Server a PostgreSQL, solo cambia este archivo
"""

import pyodbc
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from app.domain.models.medicion import Medicion
from app.domain.repositories.medicion_repository import MedicionRepository


# ---------------------------------------------------------------------------
# Queries — fuente única de verdad para el SQL
# Separados del código Python para facilitar revisión y mantenimiento
# ---------------------------------------------------------------------------

_TABLE = "dbo.Mediciones"

_SQL_SELECT_ALL = f"""
    SELECT
        fecha,
        punto_medida,
        volumen_m3,
        presion_psi,
        temperatura_c,
        calidad_gas,
        operador,
        errores
    FROM {_TABLE}
    ORDER BY fecha DESC
"""

_SQL_SELECT_POR_PUNTO = f"""
    SELECT
        fecha, punto_medida, volumen_m3,
        presion_psi, temperatura_c, calidad_gas,
        operador, errores
    FROM {_TABLE}
    WHERE punto_medida = ?
    ORDER BY fecha DESC
"""

_SQL_SELECT_POR_RANGO = f"""
    SELECT
        fecha, punto_medida, volumen_m3,
        presion_psi, temperatura_c, calidad_gas,
        operador, errores
    FROM {_TABLE}
    WHERE fecha BETWEEN ? AND ?
    ORDER BY fecha DESC
"""

_SQL_INSERT = f"""
    INSERT INTO {_TABLE} (
        fecha,
        punto_medida,
        volumen_m3,
        presion_psi,
        temperatura_c,
        calidad_gas,
        operador,
        errores
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

_SQL_DELETE_POR_PUNTO = f"""
    DELETE FROM {_TABLE}
    WHERE punto_medida = ?
"""

_SQL_COUNT_POR_PUNTO = f"""
    SELECT COUNT(*) FROM {_TABLE}
    WHERE punto_medida = ?
"""


class SqlMedicionRepository(MedicionRepository):
    """
    Repositorio de Mediciones sobre SQL Server via pyodbc.

    Parameters
    ----------
    connection_string : str
        Connection string de pyodbc. Ejemplos:

        SQL Server con autenticación Windows:
        "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=GasDB;Trusted_Connection=yes"

        SQL Server con usuario y contraseña:
        "DRIVER={ODBC Driver 17 for SQL Server};SERVER=host;DATABASE=GasDB;UID=user;PWD=pass"

    Ejemplo de uso
    --------------
    >>> repo = SqlMedicionRepository(settings.DB_CONNECTION_STRING)
    >>> mediciones = repo.obtener_todas()
    >>> repo.guardar_lote(validas)
    """

    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    # ------------------------------------------------------------------
    # Context manager de conexión — garantiza cierre siempre
    # ------------------------------------------------------------------

    @contextmanager
    def _conectar(self) -> Generator[pyodbc.Connection, None, None]:
        """
        Abre una conexión, la yield y la cierra en finally.

        Uso:
            with self._conectar() as conn:
                cursor = conn.cursor()
                ...

        autocommit=False por defecto → se necesita conn.commit() explícito.
        En caso de excepción, el context manager hace rollback automático
        al cerrar la conexión sin commit.
        """
        conn = pyodbc.connect(self._connection_string, autocommit=False)
        try:
            yield conn
        except pyodbc.Error:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    def obtener_todas(self) -> list[Medicion]:
        """
        Retorna todas las mediciones de la tabla, ordenadas por fecha DESC.

        Raises
        ------
        pyodbc.Error
            Si hay un error de conexión o en la ejecución del query.
        """
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(_SQL_SELECT_ALL)
            return [self._fila_a_entidad(row) for row in cursor.fetchall()]

    def obtener_por_punto(self, punto_medida: str) -> list[Medicion]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(_SQL_SELECT_POR_PUNTO, punto_medida.strip().upper())
            return [self._fila_a_entidad(row) for row in cursor.fetchall()]

    def obtener_por_rango_fecha(
        self,
        fecha_inicio: datetime,
        fecha_fin: datetime,
    ) -> list[Medicion]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(_SQL_SELECT_POR_RANGO, fecha_inicio, fecha_fin)
            return [self._fila_a_entidad(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def guardar(self, medicion: Medicion) -> None:
        """
        Inserta una sola medición. Usa transacción explícita.

        Raises
        ------
        pyodbc.Error
            Si falla la inserción. El rollback ocurre automáticamente
            en el context manager _conectar().
        """
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(_SQL_INSERT, self._entidad_a_tupla(medicion))
            conn.commit()

    def guardar_lote(self, mediciones: list[Medicion]) -> None:
        """
        Inserta una lista de mediciones en una sola transacción.

        Usa executemany() — mucho más eficiente que N llamadas a execute().
        Si una fila falla, toda la transacción hace rollback para
        garantizar consistencia: o se insertan todas o no se inserta ninguna.

        Raises
        ------
        pyodbc.Error
            Si falla alguna inserción. Rollback automático via _conectar().
        """
        if not mediciones:
            return

        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.fast_executemany = True  # optimización de pyodbc para bulk inserts
            cursor.executemany(
                _SQL_INSERT,
                [self._entidad_a_tupla(m) for m in mediciones],
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Eliminación
    # ------------------------------------------------------------------

    def eliminar_por_punto(self, punto_medida: str) -> int:
        """
        Elimina todos los registros de un punto de medida.

        Returns
        -------
        int
            Número de filas eliminadas (cursor.rowcount).
        """
        punto = punto_medida.strip().upper()

        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(_SQL_DELETE_POR_PUNTO, punto)
            eliminadas = cursor.rowcount
            conn.commit()
            return eliminadas

    # ------------------------------------------------------------------
    # Helpers privados — mapeo SQL ↔ Medicion
    # ------------------------------------------------------------------

    @staticmethod
    def _fila_a_entidad(row: pyodbc.Row) -> Medicion:
        """
        Convierte una fila de pyodbc a una entidad Medicion.

        pyodbc retorna las columnas en el orden del SELECT,
        accesibles por índice o por nombre de columna.
        """
        errores_raw = row.errores or ""
        return Medicion(
            fecha         = row.fecha if isinstance(row.fecha, datetime)
                            else datetime.strptime(str(row.fecha), "%Y-%m-%d %H:%M:%S"),
            punto_medida  = row.punto_medida.strip().upper(),
            volumen_m3    = float(row.volumen_m3),
            presion_psi   = float(row.presion_psi),
            temperatura_c = float(row.temperatura_c),
            calidad_gas   = float(row.calidad_gas),
            operador      = row.operador.strip(),
            errores       = [e.strip() for e in errores_raw.split("|") if e.strip()],
        )

    @staticmethod
    def _entidad_a_tupla(medicion: Medicion) -> tuple:
        """
        Convierte una entidad Medicion a una tupla de parámetros para pyodbc.
        El orden debe coincidir exactamente con los ? en _SQL_INSERT.
        """
        return (
            medicion.fecha,
            medicion.punto_medida,
            medicion.volumen_m3,
            medicion.presion_psi,
            medicion.temperatura_c,
            medicion.calidad_gas,
            medicion.operador,
            " | ".join(medicion.errores) if medicion.errores else None,
        )

    def __repr__(self) -> str:
        # Oculta credenciales del connection string en logs
        cs_seguro = self._connection_string.split(";")[0]
        return f"SqlMedicionRepository(server='{cs_seguro}...')"
