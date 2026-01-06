from urllib.parse import urlparse, parse_qs
import sqlalchemy as sa
from sqlalchemy import create_engine, text


class DBFactory14:
    """
    SQLAlchemy 1.4 DB engine used inside the subprocess virtualenv.
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

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.engine = self._create_engine()

    def _create_engine(self):
        parsed = urlparse(self.dsn)
        scheme = parsed.scheme.lower()

        # Strip driver suffix (e.g., mysql+pymysql → mysql, postgresql+psycopg2 → postgresql)
        base_scheme = scheme.split('+')[0]

        if base_scheme not in self.DIALECT_MAP:
            raise ValueError(f"Unsupported DB scheme: {base_scheme}")

        dialect = self.DIALECT_MAP[base_scheme]
        uri = self._build_sqlalchemy_uri(parsed, dialect)
        args = self._get_connect_args(parsed, base_scheme)

        # SQLAlchemy 1.4 engine creation (NO future=True)
        return create_engine(uri, connect_args=args)

    def _build_sqlalchemy_uri(self, parsed, dialect):
        if dialect.startswith("mssql"):
            qs = parse_qs(parsed.query)
            driver = qs.get("driver", ["ODBC Driver 18 for SQL Server"])[0]
            return (
                f"{dialect}://{parsed.username}:{parsed.password}"
                f"@{parsed.hostname}:{parsed.port or 1433}/{parsed.path.lstrip('/')}"
                f"?driver={driver}"
            )

        if dialect == "snowflake":
            return self.dsn.replace(parsed.scheme, dialect, 1)

        return self.dsn.replace(parsed.scheme, dialect, 1)

    def _get_connect_args(self, parsed, scheme):
        args = {}
        if scheme in ("postgres", "postgresql"):
            args["connect_timeout"] = 10
        if scheme == "sqlite":
            args["timeout"] = 10
        return args
