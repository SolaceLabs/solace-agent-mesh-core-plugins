# Changelog

## [0.1.2](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/compare/sam_sql_database_tool-0.1.1...sam_sql_database_tool-0.1.2) (2026-02-27)


### Features

* Add graceful degradation for database connection failures ([3ed1dc6](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/3ed1dc63f43566d0b80d81c8504fca95b050999d))
* Add schema recovery on reconnection + fix tests ([f4f719a](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/f4f719ab7996ea9f91d53b62c4534d21036ad9e8))
* Add self-healing connection recovery ([087bd65](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/087bd65d82f70fa5c72f456f82c4aa5305f2f2cf))
* **DATAGO-115000:** add FOSSA SCA scanning for monorepo plugins ([#79](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/79)) ([9b15f00](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/9b15f0078be038ec459dc508cfb0684a7c5c297e))
* **DATAGO-115600:** Add graceful degradation for database connection failures ([43e8e40](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/43e8e403b0455bc75a03976bc377a4e3013b73c6))
* **DATAGO-122877:** Implement MSSQL tool with pyodbc driver ([#90](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/90)) ([437f694](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/437f694d88feae424e2d91b850f4ba2baa6bd33b))
* **DATAGO-123946:** Implement OracleDB tool using oracledb library in SQL plugin ([#98](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/98)) ([4da9140](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/4da9140fe174f2a7d04a397424e6447f6b69d525))
* **DATAGO-126249:** Expose connection details in the agent configurations ([#104](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/104)) ([5f1ef27](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/5f1ef27f5592e14b4bfcf318720249b24b4ff2a1))


### Bug Fixes

* **DATAGO-113170:** Default to sql for session service ([#59](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/59)) ([983d31c](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/983d31ceb2c9902f977fd5981f5c52cd271f3476))
* **DATAGO-116435:** fix INSERT/UPDATE/DELETE operations not persisting data ([#68](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/68)) ([5fa44ce](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/5fa44ce58336513678141244a5c3b64be1f439d6))
* **DATAGO-119527:** Add connection string validation for SQL connector ([#101](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/101)) ([70827ad](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/70827ad86419a2a2c1f76b1044326b7a577a0224))


### Documentation

* **DATAGO-126743:** Improve/update MSSQL database tool documentation ([#109](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/109)) ([fcccfd3](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/fcccfd3498418f07009740a2071b4f8a08d99861))
