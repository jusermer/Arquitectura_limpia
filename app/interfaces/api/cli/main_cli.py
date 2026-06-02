"""
interfaces/cli/main_cli.py

Interfaz de línea de comandos (CLI) para ejecutar el pipeline de mediciones.

Responsabilidades:
- Proveer comandos ejecutables desde la terminal
- Inyectar dependencias de infraestructura (repositorios)
- Mostrar resultados de forma legible en consola
- Ser el punto de entrada alternativo a la API

Reglas Clean Architecture:
- Es un adaptador de entrada, igual que la API
- No contiene lógica de negocio
- Los casos de uso y repositorios se ensamblan aquí

Uso:
    python -m app.interfaces.cli.main_cli procesar
    python -m app.interfaces.cli.main_cli listar
    python -m app.interfaces.cli.main_cli listar --punto EST-BOG-01
    python -m app.interfaces.cli.main_cli registrar
"""

import click
from datetime import datetime

from app.infrastructure.config.settings import settings
from app.infrastructure.persistence.csv_repository import CsvMedicionRepository
from app.infrastructure.persistence.sql_repository import SqlMedicionRepository
from app.application.use_cases.limpiar_mediciones import LimpiarMediciones
from app.application.dtos.medicion_dto import MedicionDTO, MedicionCreateDTO


# ---------------------------------------------------------------------------
# Helpers de presentación — solo formateo para consola
# ---------------------------------------------------------------------------

def _linea(char: str = "─", ancho: int = 60) -> str:
    return char * ancho


def _encabezado(titulo: str) -> None:
    click.echo("")
    click.echo(_linea("═"))
    click.echo(f"  {titulo}")
    click.echo(_linea("═"))


def _seccion(titulo: str) -> None:
    click.echo("")
    click.echo(click.style(f"  {titulo}", fg="cyan", bold=True))
    click.echo(_linea())


def _ok(msg: str) -> None:
    click.echo(click.style(f"  ✓  {msg}", fg="green"))


def _error(msg: str) -> None:
    click.echo(click.style(f"  ✗  {msg}", fg="red"))


def _info(msg: str) -> None:
    click.echo(f"      {msg}")


def _advertencia(msg: str) -> None:
    click.echo(click.style(f"  ⚠  {msg}", fg="yellow"))


# ---------------------------------------------------------------------------
# Factories de repositorios — reutilizables entre comandos
# ---------------------------------------------------------------------------

def _repo_fuente():
    return CsvMedicionRepository(settings.paths.raw_mediciones)

def _repo_sql():
    return SqlMedicionRepository(settings.db.connection_string)

def _repo_rechazos():
    return CsvMedicionRepository(settings.paths.mediciones_invalidas)

def _repo_limpias():
    return CsvMedicionRepository(settings.paths.mediciones_limpias)


# ---------------------------------------------------------------------------
# Grupo principal de comandos
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(version="1.0.0", prog_name="macrom-cli")
def cli():
    """
    MaCRoM CLI — Gestión de mediciones de gas.

    Comandos disponibles:

    \b
      procesar   Ejecuta el pipeline completo de limpieza y carga
      listar     Lista las mediciones del CSV fuente
      registrar  Registra una nueva medición manualmente
    """
    pass


# ---------------------------------------------------------------------------
# Comando: procesar
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--dry-run",
    is_flag = True,
    default = False,
    help    = "Simula el proceso sin persistir datos.",
)
def procesar(dry_run: bool):
    """
    Ejecuta el pipeline completo de limpieza y carga.

    Lee el CSV fuente, valida las mediciones, carga las válidas
    a SQL Server y guarda las inválidas en el CSV de rechazos.
    """
    _encabezado("Pipeline de limpieza y carga — MaCRoM")

    if dry_run:
        _advertencia("Modo DRY RUN activado — no se persistirá ningún dato.")

    click.echo(f"\n  Fuente   : {settings.paths.raw_mediciones}")
    click.echo(f"  Destino  : {settings.db.server} / {settings.db.database}")
    click.echo(f"  Rechazos : {settings.paths.mediciones_invalidas}")

    # Confirmación antes de ejecutar en producción
    if settings.app.es_produccion and not dry_run:
        click.confirm(
            "\n  ¿Confirmas la ejecución en PRODUCCIÓN?",
            abort = True,
        )

    _seccion("Ejecutando pipeline...")

    caso_uso = LimpiarMediciones(
        repo_fuente   = _repo_fuente(),
        repo_sql      = _repo_sql() if not dry_run else _repo_limpias(),
        repo_rechazos = _repo_rechazos() if not dry_run else _repo_limpias(),
    )

    resultado = caso_uso.ejecutar()

    # ── Resultado ───────────────────────────────────────────────────
    _seccion("Resultado")

    click.echo(f"  {'Mediciones leídas':<25} {resultado.total_leidas}")
    click.echo(f"  {'Mediciones válidas':<25} {resultado.total_validas}")
    click.echo(f"  {'Mediciones inválidas':<25} {resultado.total_invalidas}")

    if resultado.carga_sql:
        click.echo(f"  {'Cargadas a SQL':<25} {resultado.carga_sql.total_cargadas}")
        click.echo(f"  {'Fallidas en SQL':<25} {resultado.carga_sql.total_fallidas}")

    if resultado.duracion_segundos is not None:
        click.echo(f"  {'Duración':<25} {resultado.duracion_segundos}s")

    # ── Resumen por punto ───────────────────────────────────────────
    if resultado.resumen and resultado.resumen.por_punto:
        _seccion("Resumen por punto de medida")
        for punto in resultado.resumen.por_punto:
            estado = click.style("OK", fg="green") if punto.total_invalidas == 0 \
                     else click.style(f"{punto.tasa_invalidez}% invalidas", fg="yellow")
            click.echo(
                f"  {punto.punto_medida:<20} "
                f"total={punto.total_mediciones:<6} "
                f"vol={punto.volumen_total_m3:<10.2f} m³  {estado}"
            )

    # ── Errores del pipeline ────────────────────────────────────────
    if resultado.errores_pipeline:
        _seccion("Errores del pipeline")
        for err in resultado.errores_pipeline:
            _error(err)

    # ── Estado final ────────────────────────────────────────────────
    click.echo("")
    if resultado.fue_exitoso:
        _ok("Pipeline completado exitosamente.")
    else:
        _advertencia("Pipeline finalizado con errores. Revisa los detalles arriba.")

    click.echo(_linea("═"))
    click.echo("")


# ---------------------------------------------------------------------------
# Comando: listar
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--punto",
    default = None,
    help    = "Filtrar por punto de medida (ej: EST-BOG-01).",
)
@click.option(
    "--solo-invalidas",
    is_flag = True,
    default = False,
    help    = "Mostrar solo las mediciones con errores.",
)
def listar(punto: str | None, solo_invalidas: bool):
    """
    Lista las mediciones del CSV fuente.

    Muestra fecha, punto, volumen, presión, temperatura y estado.
    """
    _encabezado("Mediciones — MaCRoM")

    repo = _repo_fuente()

    mediciones = (
        repo.obtener_por_punto(punto)
        if punto
        else repo.obtener_todas()
    )

    if not mediciones:
        _advertencia("No se encontraron mediciones.")
        return

    dtos = MedicionDTO.lista_desde_entidades(mediciones)

    if solo_invalidas:
        dtos = [d for d in dtos if not d.es_valida]

    if not dtos:
        _advertencia("No hay mediciones que coincidan con los filtros.")
        return

    # ── Encabezado de tabla ─────────────────────────────────────────
    click.echo("")
    click.echo(
        f"  {'Fecha':<22}"
        f"{'Punto':<18}"
        f"{'Vol m³':>8}"
        f"{'Psi':>7}"
        f"{'°C':>6}"
        f"{'Calidad':>9}"
        f"  {'Estado'}"
    )
    click.echo(_linea())

    # ── Filas ───────────────────────────────────────────────────────
    for dto in dtos:
        estado = (
            click.style("VÁLIDA", fg="green")
            if dto.es_valida
            else click.style("INVÁLIDA", fg="red")
        )
        click.echo(
            f"  {dto.fecha:<22}"
            f"{dto.punto_medida:<18}"
            f"{dto.volumen_m3:>8.2f}"
            f"{dto.presion_psi:>7.1f}"
            f"{dto.temperatura_c:>6.1f}"
            f"{dto.calidad_gas:>9.3f}"
            f"  {estado}"
        )
        if not dto.es_valida and dto.errores:
            for err in dto.errores:
                _info(click.style(f"↳ {err}", fg="red"))

    click.echo(_linea())
    click.echo(f"\n  Total: {len(dtos)} mediciones")
    click.echo("")


# ---------------------------------------------------------------------------
# Comando: registrar
# ---------------------------------------------------------------------------

@cli.command()
def registrar():
    """
    Registra una nueva medición de forma interactiva.

    Solicita los datos por consola, valida y persiste.
    """
    _encabezado("Registrar medición — MaCRoM")
    click.echo("  Ingresa los datos de la nueva medición:\n")

    try:
        punto_medida  = click.prompt("  Punto de medida (ej: EST-BOG-01)")
        volumen_m3    = click.prompt("  Volumen (m³)",      type=float)
        presion_psi   = click.prompt("  Presión (psi)",     type=float)
        temperatura_c = click.prompt("  Temperatura (°C)",  type=float)
        calidad_gas   = click.prompt("  Calidad del gas (0.85–1.00)", type=float)
        operador      = click.prompt("  Operador")

    except click.Abort:
        click.echo("\n  Operación cancelada.")
        return

    # Construir DTO y convertir a entidad
    from app.domain.services.reglas_validacion import validar_medicion

    create_dto = MedicionCreateDTO(
        punto_medida  = punto_medida,
        volumen_m3    = volumen_m3,
        presion_psi   = presion_psi,
        temperatura_c = temperatura_c,
        calidad_gas   = calidad_gas,
        operador      = operador,
        fecha         = datetime.utcnow(),
    )

    medicion  = create_dto.a_entidad()
    es_valida = validar_medicion(medicion)

    _seccion("Resultado de validación")

    if es_valida:
        _ok("Medición válida. Guardando en SQL Server...")
        _repo_sql().guardar(medicion)
        _ok("Medición guardada exitosamente.")
    else:
        _error("Medición inválida. Errores encontrados:")
        for err in medicion.errores:
            _info(f"↳ {err}")
        _advertencia("Guardando en CSV de rechazos...")
        _repo_rechazos().guardar(medicion)
        _advertencia("Medición guardada en rechazos.")

    click.echo("")


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
