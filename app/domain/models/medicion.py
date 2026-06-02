"""
domain/models/medicion.py

Entidad central del dominio. Representa una medición de gas.
- Sin imports de librerías externas (pandas, sqlalchemy, pyodbc, etc.)
- Sin lógica de persistencia ni de presentación
- Solo estructura de datos + validaciones de negocio puras
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class EstadoMedicion(Enum):
    """Estados posibles de una medición dentro del dominio."""
    PENDIENTE   = "pendiente"    # recién ingresada, sin validar
    VALIDA      = "valida"       # pasó todas las reglas de negocio
    INVALIDA    = "invalida"     # falló una o más reglas
    PROCESADA   = "procesada"   # ya fue cargada al sistema destino


@dataclass
class Medicion:
    """
    Entidad de dominio: medición de gas.

    Atributos
    ---------
    id_medicion     : Identificador único (str para no acoplar al tipo de BD).
    equipo_id       : ID del equipo que registró la medición.
    timestamp       : Momento exacto de la medición (UTC).
    valor_kwh       : Valor energético medido en kWh.
    presion_bar     : Presión registrada en bar.
    temperatura_c   : Temperatura en grados Celsius.
    unidad          : Unidad de medida del valor principal (default 'kWh').
    estado          : Estado actual dentro del ciclo de vida del dominio.
    errores         : Lista de mensajes de error acumulados durante validación.
    """

    id_medicion   : str
    equipo_id     : str
    timestamp     : datetime
    valor_kwh     : float
    presion_bar   : float
    temperatura_c : float
    unidad        : str                  = "kWh"
    estado        : EstadoMedicion       = EstadoMedicion.PENDIENTE
    errores       : list[str]            = field(default_factory=list)

    # ------------------------------------------------------------------
    # Reglas de negocio básicas (invariantes de la entidad)
    # Reglas más complejas o que cruzan entidades van en domain/services/
    # ------------------------------------------------------------------

    def es_valor_positivo(self) -> bool:
        """El valor medido no puede ser negativo ni cero."""
        return self.valor_kwh > 0

    def es_presion_valida(self) -> bool:
        """La presión debe estar en un rango operacional razonable (0 – 200 bar)."""
        return 0 < self.presion_bar <= 200

    def es_temperatura_valida(self) -> bool:
        """Temperatura operacional admitida: -40 °C a 150 °C."""
        return -40 <= self.temperatura_c <= 150

    def es_timestamp_valido(self) -> bool:
        """El timestamp no puede ser una fecha futura."""
        return self.timestamp <= datetime.utcnow()

    # ------------------------------------------------------------------
    # Transiciones de estado
    # ------------------------------------------------------------------

    def marcar_valida(self) -> None:
        """Transiciona la medición al estado VALIDA y limpia errores previos."""
        self.estado  = EstadoMedicion.VALIDA
        self.errores = []

    def marcar_invalida(self, motivos: list[str]) -> None:
        """
        Transiciona la medición al estado INVALIDA y registra los motivos.

        Parameters
        ----------
        motivos : list[str]
            Descripciones de las reglas que fallaron.
        """
        if not motivos:
            raise ValueError("Se deben indicar los motivos de invalidación.")
        self.estado  = EstadoMedicion.INVALIDA
        self.errores = motivos

    def marcar_procesada(self) -> None:
        """
        Transiciona al estado PROCESADA.
        Solo se permite desde el estado VALIDA.
        """
        if self.estado is not EstadoMedicion.VALIDA:
            raise ValueError(
                f"Solo se puede procesar una medición válida. "
                f"Estado actual: {self.estado.value}"
            )
        self.estado = EstadoMedicion.PROCESADA

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def tiene_errores(self) -> bool:
        return len(self.errores) > 0

    def __str__(self) -> str:
        return (
            f"Medicion(id={self.id_medicion}, equipo={self.equipo_id}, "
            f"valor={self.valor_kwh} {self.unidad}, estado={self.estado.value})"
        )