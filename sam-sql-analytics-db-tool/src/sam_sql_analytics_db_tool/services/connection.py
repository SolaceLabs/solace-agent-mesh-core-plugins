from dataclasses import dataclass
from typing import Dict, Any, List
from urllib.parse import urlparse, parse_qs
import logging

from sqlalchemy import create_engine, text
import sqlalchemy as sa

log = logging.getLogger(__name__)


@dataclass
class DBFactory:
    """
    Main-process SQLAlchemy 2.x DB engine.
    Used ONLY for executing SELECT queries after profiling.
    """
  
    DIALECT_MAP = {
        "postgres": "postgresql+psycopg2",
        "postgresql": "postgresql+psycopg2",
        "mysql": "mysql+pymysql",
        "mariadb": "mysql+pymysql",
        "sqlite": "sqlite",
        "mssql": "mssql+pyodbc",
        "sqlserver": "mssql+pyodbc",
        "oracle": "oracle+oracledb",
        "snowflake": "snowflake",
    }

    def __init__(self, connection_string: str, pool_config: Dict[str, Any], timeouts: Dict[str, Any]):
        self.connection_string = connection_string
        self.pool_config = pool_config
        self.timeouts = timeouts
        self.engine = self._create_engine()


    def _create_engine(self) -> sa.Engine:
        parsed = urlparse(self.connection_string)
        scheme = parsed.scheme.lower()

        # Strip driver suffix (e.g., mysql+pymysql → mysql, postgresql+psycopg2 → postgresql)
        base_scheme = scheme.split('+')[0]

        if base_scheme not in self.DIALECT_MAP:
            raise ValueError(f"Unsupported database type: {base_scheme}")

        dialect = self.DIALECT_MAP[base_scheme]
        sqlalchemy_uri = self._build_sqlalchemy_uri(parsed, dialect)
        connect_args = self._get_connect_args(parsed, base_scheme)

        engine = create_engine(
            sqlalchemy_uri,
            pool_size=self.pool_config.get("pool_size", 5),
            max_overflow=self.pool_config.get("max_overflow", 5),
            pool_timeout=self.pool_config.get("pool_timeout", 30),
            pool_recycle=self.pool_config.get("pool_recycle", 1800),
            pool_pre_ping=self.pool_config.get("pool_pre_ping", True),
            connect_args=connect_args,
            future=True
        )

        log.info("DBFactory created engine for: %s://%s", base_scheme, parsed.hostname)
        return engine

    # ----------------------------------------------------------------------
    # URI Construction
    # ----------------------------------------------------------------------

    def _build_sqlalchemy_uri(self, parsed, dialect: str) -> str:

        # MSSQL ODBC
        if dialect.startswith("mssql"):
            qs = parse_qs(parsed.query)
            driver = qs.get("driver", ["ODBC Driver 18 for SQL Server"])[0]

            extra = [f"{k}={v[0]}" for k, v in qs.items() if k != "driver"]
            extra_params = "&".join(extra)

            uri = (
                f"{dialect}://{parsed.username}:{parsed.password}"
                f"@{parsed.hostname}:{parsed.port or 1433}/{parsed.path.lstrip('/')}"
                f"?driver={driver}"
            )
            if extra_params:
                uri += f"&{extra_params}"

            return uri

        # Snowflake — swap only the scheme
        if dialect == "snowflake":
            return self.connection_string.replace(parsed.scheme, dialect, 1)

        # Default — replace dialect in scheme
        return self.connection_string.replace(parsed.scheme, dialect, 1)

    # ----------------------------------------------------------------------
    # DB-specific connect args
    # ----------------------------------------------------------------------

    def _get_connect_args(self, parsed, scheme: str) -> Dict[str, Any]:
        args = {}

        if scheme in ("postgres", "postgresql"):
            args["connect_timeout"] = self.timeouts.get("connect_timeout", 10)
            args["options"] = f"-c statement_timeout={self.timeouts.get('statement_timeout_ms', 30000)}"

        elif scheme in ("mysql", "mariadb"):
            args["connect_timeout"] = self.timeouts.get("connect_timeout", 10)

        elif scheme in ("mssql", "sqlserver"):
            qs = parse_qs(parsed.query)
            args["timeout"] = int(qs.get("timeout", [self.timeouts.get("connect_timeout", 10)])[0])

        elif scheme == "oracle":
            # Oracle usually handles timeouts via DSN or pool
            pass

        elif scheme == "snowflake":
            args["login_timeout"] = self.timeouts.get("connect_timeout", 10)
            args["network_timeout"] = self.timeouts.get("connect_timeout", 10)

        elif scheme == "sqlite":
            args["timeout"] = self.timeouts.get("connect_timeout", 10)

        return args

    # ----------------------------------------------------------------------
    # QUERY EXECUTION (NO SECURITY HERE — validated beforehand)
    # ----------------------------------------------------------------------

    def run_select(self, sql: str, limit: int = None) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query (security is already handled by SecurityService).

        Args:
            sql: SQL query to execute
            limit: optional enforced row limit

        Returns:
            list of dict rows
        """
        if limit:
            sql = sql.rstrip(";")
            if "limit" not in sql.lower() and "fetch" not in sql.lower():
                sql += f" LIMIT {limit}"

        with self.engine.connect() as conn:
            result = conn.execute(text(sql))
            return [dict(row._mapping) for row in result]

    def close(self):
        """Dispose engine + pool."""
        try:
            self.engine.dispose()
        except Exception:
            pass
