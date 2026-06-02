"""
infrastructure/config/settings.py

Configuración centralizada de la aplicación.

Responsabilidades:
- Leer variables de entorno (.env o sistema operativo)
- Proveer valores por defecto seguros para desarrollo
- Construir objetos de configuración tipados
- Ser la única fuente de verdad para parámetros de infraestructura

Reglas Clean Architecture:
- Solo se importa desde infrastructure/ e interfaces/
- NUNCA se importa desde domain/ ni application/
- La configuración se inyecta hacia adentro, nunca se jala desde adentro

Uso:
    from app.infrastructure.config.settings import settings

    repo = SqlMedicionRepository(settings.db_connection_string)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Carga del archivo .env
# Se busca en la raíz del proyecto (dos niveles arriba de este archivo)
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # raíz del proyecto
_ENV_FILE = _BASE_DIR / ".env"

load_dotenv(dotenv_path=_ENV_FILE)


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _get(key: str, default: str = "") -> str:
    """Lee una variable de entorno. Lanza error si es requerida y no existe."""
    value = os.getenv(key, default).strip()
    return value


def _get_required(key: str) -> str:
    """
    Lee una variable de entorno requerida.

    Raises
    ------
    EnvironmentError
        Si la variable no está definida o está vacía.
    """
    value = os.getenv(key, "").strip()
    if not value:
        raise EnvironmentError(
            f"Variable de entorno requerida no encontrada: '{key}'. "
            f"Verifica tu archivo .env o las variables del sistema."
        )
    return value


def _get_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _get_bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Dataclasses de configuración por dominio
# Cada sección agrupa parámetros relacionados
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DatabaseConfig:
    """Configuración de conexión a SQL Server."""
    driver   : str
    server   : str
    database : str
    username : str
    password : str
    port     : int
    timeout  : int

    @property
    def connection_string(self) -> str:
        """
        Construye el connection string para pyodbc.

        Con autenticación SQL (usuario + contraseña):
            DRIVER=...;SERVER=host,1433;DATABASE=db;UID=user;PWD=pass;Connection Timeout=30
        """
        return (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.server},{self.port};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            f"Connection Timeout={self.timeout};"
        )

    @property
    def connection_string_windows_auth(self) -> str:
        """Connection string con autenticación Windows (sin usuario/contraseña)."""
        return (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.server},{self.port};"
            f"DATABASE={self.database};"
            f"Trusted_Connection=yes;"
            f"Connection Timeout={self.timeout};"
        )

    def __repr__(self) -> str:
        """Oculta la contraseña en logs y debug."""
        return (
            f"DatabaseConfig("
            f"server={self.server}, "
            f"database={self.database}, "
            f"username={self.username}, "
            f"password=***)"
        )


@dataclass(frozen=True)
class PathsConfig:
    """Rutas de archivos CSV del proyecto."""
    raw_mediciones    : Path
    mediciones_limpias : Path
    mediciones_invalidas: Path
    reporte_resumen   : Path

    def __post_init__(self) -> None:
        # Verificar que la carpeta raw existe al iniciar
        if not self.raw_mediciones.parent.exists():
            raise FileNotFoundError(
                f"Directorio de datos no encontrado: '{self.raw_mediciones.parent}'. "
                f"Verifica la variable DATA_DIR en tu .env"
            )


@dataclass(frozen=True)
class AppConfig:
    """Configuración general de la aplicación."""
    entorno       : str   # "development" | "staging" | "production"
    debug         : bool
    log_level     : str   # "DEBUG" | "INFO" | "WARNING" | "ERROR"
    api_host      : str
    api_port      : int
    api_prefix    : str

    @property
    def es_produccion(self) -> bool:
        return self.entorno == "production"

    @property
    def es_desarrollo(self) -> bool:
        return self.entorno == "development"


# ---------------------------------------------------------------------------
# Configuración principal — singleton construido al importar el módulo
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Settings:
    """
    Objeto principal de configuración. Singleton de la aplicación.

    Se construye una sola vez al importar el módulo.
    Todas las capas de infrastructure/ e interfaces/ usan esta instancia.

    Ejemplo
    -------
    >>> from app.infrastructure.config.settings import settings
    >>> repo = SqlMedicionRepository(settings.db.connection_string)
    >>> repo_csv = CsvMedicionRepository(settings.paths.raw_mediciones)
    """
    app   : AppConfig
    db    : DatabaseConfig
    paths : PathsConfig


def _build_settings() -> Settings:
    """
    Construye el objeto Settings leyendo las variables de entorno.
    Se llama una sola vez al importar el módulo.
    """
    data_dir = Path(_get("DATA_DIR", str(_BASE_DIR / "data")))

    app = AppConfig(
        entorno    = _get("APP_ENV", "development"),
        debug      = _get_bool("APP_DEBUG", True),
        log_level  = _get("LOG_LEVEL", "INFO").upper(),
        api_host   = _get("API_HOST", "0.0.0.0"),
        api_port   = _get_int("API_PORT", 8000),
        api_prefix = _get("API_PREFIX", "/api/v1"),
    )

    db = DatabaseConfig(
        driver   = _get("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
        server   = _get_required("DB_SERVER"),
        database = _get_required("DB_NAME"),
        username = _get_required("DB_USER"),
        password = _get_required("DB_PASSWORD"),
        port     = _get_int("DB_PORT", 1433),
        timeout  = _get_int("DB_TIMEOUT", 30),
    )

    paths = PathsConfig(
        raw_mediciones      = data_dir / "raw"       / _get("FILE_RAW",      "mediciones_gas.csv"),
        mediciones_limpias  = data_dir / "processed" / _get("FILE_LIMPIAS",  "mediciones_limpias.csv"),
        mediciones_invalidas= data_dir / "processed" / _get("FILE_INVALIDAS","mediciones_invalidas.csv"),
        reporte_resumen     = data_dir / "reports"   / _get("FILE_RESUMEN",  "resumen_mediciones.csv"),
    )

    return Settings(app=app, db=db, paths=paths)


# Instancia singleton — se importa directamente desde otros módulos
settings: Settings = _build_settings()
