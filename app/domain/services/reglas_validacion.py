"""
domain/services/reglas_validacion.py

Servicio de dominio: orquesta la validación de una Medicion.

Responsabilidades:
- Ejecutar todas las reglas de negocio sobre una Medicion
- Acumular los mensajes de error
- Decidir si la medición es válida o inválida
- Mutar el estado de la entidad (errores) una sola vez, desde un único lugar

Reglas Clean Architecture:
- Solo importa del propio dominio (models/)
- Sin pandas, pyodbc, SQLAlchemy ni ninguna librería externa
- Sin lógica de persistencia ni de presentación
"""

from app.domain.models.medicion import Medicion


# ---------------------------------------------------------------------------
# Reglas individuales
# Cada regla es una función pura: recibe Medicion, devuelve str | None
# None  → regla pasó
# str   → mensaje de error listo para mostrar
# ---------------------------------------------------------------------------

def _validar_fecha(m: Medicion) -> str | None:
    if not m.fecha_valida():
        from datetime import datetime
        if m.fecha > datetime.utcnow():
            return "La fecha no puede ser futura."
        return "La fecha es demasiado antigua (antes del año 2000)."
    return None


def _validar_volumen(m: Medicion) -> str | None:
    if not m.es_valor_positivo():
        return f"El volumen debe ser mayor que cero. Valor recibido: {m.volumen_m3}."
    return None


def _validar_presion(m: Medicion) -> str | None:
    if not m.es_presion_valida():
        return (
            f"La presión está fuera del rango permitido (20–80 psi). "
            f"Valor recibido: {m.presion_psi} psi."
        )
    return None


def _validar_temperatura(m: Medicion) -> str | None:
    if not m.es_temperatura_valida():
        return (
            f"La temperatura está fuera del rango permitido (-10 a 60 °C). "
            f"Valor recibido: {m.temperatura_c} °C."
        )
    return None


def _validar_calidad_gas(m: Medicion) -> str | None:
    if not m.es_calidad_gas_valida():
        return (
            f"La calidad del gas debe estar entre 0.85 y 1.00. "
            f"Valor recibido: {m.calidad_gas}."
        )
    return None


# Registro de reglas — fácil de extender sin tocar la lógica principal
_REGLAS = [
    _validar_fecha,
    _validar_volumen,
    _validar_presion,
    _validar_temperatura,
    _validar_calidad_gas,
]


# ---------------------------------------------------------------------------
# Punto de entrada principal
# ---------------------------------------------------------------------------

def validar_medicion(medicion: Medicion) -> bool:
    """
    Ejecuta todas las reglas de negocio sobre una Medicion.

    Efectos:
    - Popula medicion.errores con los mensajes de las reglas que fallaron.
    - No lanza excepciones — los errores se acumulan para ser consultados.

    Returns
    -------
    bool
        True  → medición válida (sin errores)
        False → medición inválida (medicion.errores contiene los motivos)

    Ejemplo
    -------
    >>> es_valida = validar_medicion(m)
    >>> if not es_valida:
    ...     print(m.errores)
    """
    # Limpiar errores previos para que sea idempotente
    medicion.errores.clear()

    for regla in _REGLAS:
        error = regla(medicion)
        if error:
            medicion.errores.append(error)

    return not medicion.tiene_errores()


def validar_lote(mediciones: list[Medicion]) -> tuple[list[Medicion], list[Medicion]]:
    """
    Valida una lista de mediciones y las separa en válidas e inválidas.

    Returns
    -------
    tuple[list[Medicion], list[Medicion]]
        (validas, invalidas)

    Ejemplo
    -------
    >>> validas, invalidas = validar_lote(mediciones)
    >>> print(f"{len(validas)} válidas, {len(invalidas)} inválidas")
    """
    validas   : list[Medicion] = []
    invalidas : list[Medicion] = []

    for medicion in mediciones:
        if validar_medicion(medicion):
            validas.append(medicion)
        else:
            invalidas.append(medicion)

    return validas, invalidas
