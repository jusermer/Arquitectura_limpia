"""
infrastructure/persistence/csv_repository.py

Implementación concreta del puerto MedicionRepository para archivos CSV.

Responsabilidades:
- Leer mediciones desde un archivo CSV (raw o procesado)
- Escribir mediciones válidas e inválidas a archivos CSV
- Mapear entre filas CSV y entidades de dominio (Medicion)

Reglas Clean Architecture:
- Implementa MedicionRepository (puerto del dominio)
- El dominio NO conoce este archivo — la dependencia va hacia adentro
- Toda la lógica de CSV (parsing, encoding, headers) queda aquí
- Si el formato del CSV cambia, solo cambia este archivo
"""

import csv
import os
from datetime import datetime
from pathlib import Path

from app.domain.models.medicion import Medicion
from app.domain.repositories.medicion_repository import MedicionRepository


# Columnas esperadas en el CSV — fuente única de verdad para el mapeo
_HEADERS = [
    "fecha",
    "punto_medida",
    "volumen_m3",
    "presion_psi",
    "temperatura_c",
    "calidad_gas",
    "operador",
    "errores",
]

_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_ENCODING        = "utf-8-sig"   # utf-8-sig maneja el BOM de archivos Excel


class CsvMedicionRepository(MedicionRepository):
    """
    Repositorio de Mediciones sobre archivos CSV.

    Parameters
    ----------
    ruta_archivo : str | Path
        Ruta absoluta o relativa al archivo CSV.
        Si el archivo no existe al escribir, se crea automáticamente.

    Ejemplo de uso
    --------------
    >>> repo = CsvMedicionRepository("data/raw/mediciones_gas.csv")
    >>> mediciones = repo.obtener_todas()
    >>> print(f"{len(mediciones)} mediciones leídas")

    >>> repo_out = CsvMedicionRepository("data/processed/mediciones_limpias.csv")
    >>> repo_out.guardar_lote(validas)
    """

    def __init__(self, ruta_archivo: str | Path) -> None:
        self._ruta = Path(ruta_archivo)

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    def obtener_todas(self) -> list[Medicion]:
        """
        Lee todas las mediciones del CSV.

        Returns
        -------
        list[Medicion]
            Lista de entidades. Vacía si el archivo no existe o está vacío.

        Raises
        ------
        ValueError
            Si una fila tiene datos que no pueden convertirse al tipo esperado.
        """
        if not self._ruta.exists():
            return []

        mediciones: list[Medicion] = []

        with open(self._ruta, encoding=_ENCODING, newline="") as f:
            reader = csv.DictReader(f)
            for numero_fila, fila in enumerate(reader, start=2):  # start=2: fila 1 es el header
                try:
                    medicion = self._fila_a_entidad(fila)
                    mediciones.append(medicion)
                except (ValueError, KeyError) as e:
                    raise ValueError(
                        f"Error al parsear fila {numero_fila} "
                        f"en '{self._ruta}': {e}"
                    ) from e

        return mediciones

    def obtener_por_punto(self, punto_medida: str) -> list[Medicion]:
        return [
            m for m in self.obtener_todas()
            if m.punto_medida == punto_medida.strip().upper()
        ]

    def obtener_por_rango_fecha(
        self,
        fecha_inicio: datetime,
        fecha_fin: datetime,
    ) -> list[Medicion]:
        return [
            m for m in self.obtener_todas()
            if fecha_inicio <= m.fecha <= fecha_fin
        ]

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def guardar(self, medicion: Medicion) -> None:
        """
        Agrega una medición al CSV. Crea el archivo con headers si no existe.
        """
        self._asegurar_directorio()
        archivo_nuevo = not self._ruta.exists()

        with open(self._ruta, mode="a", encoding=_ENCODING, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_HEADERS)
            if archivo_nuevo:
                writer.writeheader()
            writer.writerow(self._entidad_a_fila(medicion))

    def guardar_lote(self, mediciones: list[Medicion]) -> None:
        """
        Escribe una lista de mediciones al CSV (sobreescribe el archivo).

        Sobreescribir es el comportamiento correcto para los archivos
        processed/ — cada ejecución genera un archivo limpio.
        Para modo append, usar guardar() en un loop.
        """
        if not mediciones:
            return

        self._asegurar_directorio()

        with open(self._ruta, mode="w", encoding=_ENCODING, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_HEADERS)
            writer.writeheader()
            writer.writerows(self._entidad_a_fila(m) for m in mediciones)

    # ------------------------------------------------------------------
    # Eliminación
    # ------------------------------------------------------------------

    def eliminar_por_punto(self, punto_medida: str) -> int:
        """
        Elimina todas las filas del CSV que coincidan con el punto de medida.

        Returns
        -------
        int
            Número de registros eliminados.
        """
        todas      = self.obtener_todas()
        filtradas  = [m for m in todas if m.punto_medida != punto_medida.strip().upper()]
        eliminadas = len(todas) - len(filtradas)

        if eliminadas > 0:
            self.guardar_lote(filtradas)

        return eliminadas

    # ------------------------------------------------------------------
    # Helpers privados — mapeo CSV ↔ Medicion
    # ------------------------------------------------------------------

    @staticmethod
    def _fila_a_entidad(fila: dict[str, str]) -> Medicion:
        """
        Convierte una fila del CSV (dict de strings) a una entidad Medicion.

        Raises
        ------
        ValueError
            Si algún campo no puede convertirse al tipo esperado.
        KeyError
            Si falta una columna requerida.
        """
        errores_raw = fila.get("errores", "").strip()

        return Medicion(
            fecha         = datetime.strptime(fila["fecha"].strip(), _DATETIME_FORMAT),
            punto_medida  = fila["punto_medida"].strip().upper(),
            volumen_m3    = float(fila["volumen_m3"]),
            presion_psi   = float(fila["presion_psi"]),
            temperatura_c = float(fila["temperatura_c"]),
            calidad_gas   = float(fila["calidad_gas"]),
            operador      = fila["operador"].strip(),
            errores       = [e.strip() for e in errores_raw.split("|") if e.strip()],
        )

    @staticmethod
    def _entidad_a_fila(medicion: Medicion) -> dict[str, str]:
        """
        Convierte una entidad Medicion a una fila CSV (dict de strings).
        """
        return {
            "fecha"         : medicion.fecha.strftime(_DATETIME_FORMAT),
            "punto_medida"  : medicion.punto_medida,
            "volumen_m3"    : str(medicion.volumen_m3),
            "presion_psi"   : str(medicion.presion_psi),
            "temperatura_c" : str(medicion.temperatura_c),
            "calidad_gas"   : str(medicion.calidad_gas),
            "operador"      : medicion.operador,
            "errores"       : " | ".join(medicion.errores),
        }

    def _asegurar_directorio(self) -> None:
        """Crea el directorio del archivo si no existe."""
        self._ruta.parent.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        existe = self._ruta.exists()
        return (
            f"CsvMedicionRepository("
            f"ruta='{self._ruta}', "
            f"existe={existe})"
        )
