"""
domain/models/medicion.py
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Medicion:
    fecha         : datetime
    punto_medida  : str
    volumen_m3    : float
    presion_psi   : float
    temperatura_c : float
    calidad_gas   : float
    operador      : str

    # Manejado externamente por reglas_validacion.py
    # Solo se popula desde fuera, nunca desde los métodos de la entidad
    errores: list[str] = field(default_factory=list, repr=False)

    # Invariantes — solo evalúan, no acumulan errores
    def fecha_valida(self) -> bool:
        return datetime(2000, 1, 1) <= self.fecha <= datetime.utcnow()

    def es_valor_positivo(self) -> bool:
        return self.volumen_m3 > 0

    def es_presion_valida(self) -> bool:
        return 20 < self.presion_psi < 80

    def es_temperatura_valida(self) -> bool:
        return -10 < self.temperatura_c < 60

    def es_calidad_gas_valida(self) -> bool:
        return 0.85 <= self.calidad_gas <= 1.0

    def tiene_errores(self) -> bool:
        return len(self.errores) > 0

    def __str__(self) -> str:
        return (
            f"Medicion("
            f"fecha={self.fecha}, "
            f"punto_medida='{self.punto_medida}', "
            f"volumen_m3={self.volumen_m3}, "
            f"presion_psi={self.presion_psi}, "
            f"temperatura_c={self.temperatura_c}, "
            f"calidad_gas={self.calidad_gas}, "
            f"operador='{self.operador}'"
            f")"
        )