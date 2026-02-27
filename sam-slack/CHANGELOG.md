# Changelog

## [0.2.1](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/compare/sam_slack-0.2.0...sam_slack-0.2.1) (2026-02-27)


### Features

* **DATAGO-115000:** add FOSSA SCA scanning for monorepo plugins ([#79](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/79)) ([9b15f00](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/9b15f0078be038ec459dc508cfb0684a7c5c297e))
* refactor slack gateway to use a2a helper layer for part creation ([b7ed8b9](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/b7ed8b979392ca85aa4e01ca5a5a6e0ff27fef03))


### Bug Fixes

* correct file part handling in REST and Slack gateways ([c51e501](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/c51e50154b935c35addf73c7995cbfd0c8d95c0b))
* **DATAGO-112455:** pin dependency version ([9edcd9c](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/9edcd9c22648042dc461ee2e5c9f37311b34711c))
* Normalize email to lowercase in Slack gateway for consistent user identification ([#86](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/86)) ([ed88e1a](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/ed88e1ada877c46907942989241a1f5e3577ba48))
* pin dependencies for sam slack ([6188607](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/6188607ea9023073790bf89b5422f90e611b2b62))
* **sam-slack:** use bytes_transferred instead of bytes_saved in artifact progress ([#95](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/95)) ([5166c4a](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/5166c4abe3b7341fb301078219186e60404654dd))
* update slack to work with new base gateway ([2e289e8](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/2e289e8db5608867ad58e437b51b2c0e48c431b7))
* update slack to work with new base gateway ([38aac4d](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/38aac4d739cff838a5cf01c59c6b3e6571d3505a))
* update TaskState enum references to use lowercase values ([d252b40](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/d252b402fddb7956f67717114cf51e45997a268e))
* update the dependencies for our gateways ([19fb4f4](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/19fb4f489907f3b4c3b693b16044efd15ec2d7b7))


### Documentation

* add A2A SDK migration design document for Slack gateway ([224366b](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/224366b950d08ffec1edd08d99abe4dc04ee1c36))
* add A2A SDK migration implementation checklist ([6fec3f0](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/6fec3f03e5da823b00660d821f096dfb39d13b56))
* add A2A SDK migration implementation plan for Slack Gateway ([b60b319](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/b60b319d61a69517419acb323ef46b39324e9271))
