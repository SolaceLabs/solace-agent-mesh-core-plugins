"""
Solace Agent Mesh - SQL Database Agent Plugin
Provides natural language querying capabilities for SQL databases.

.. deprecated::
    This plugin is deprecated and may be removed in a future release.
    Please migrate to ``sam-sql-database-tool``, which offers broader database
    engine support (PostgreSQL, MySQL, MariaDB, MSSQL, Oracle), improved connection
    pooling, and active development.
"""

import warnings

warnings.warn(
    "sam-sql-database is deprecated and may be removed in a future release. "
    "Please migrate to sam-sql-database-tool for broader database engine support "
    "(PostgreSQL, MySQL, MariaDB, MSSQL, Oracle), improved connection pooling, "
    "and continued development. "
    "See the sam-sql-database-tool README for details.",
    DeprecationWarning,
    stacklevel=2,
)
