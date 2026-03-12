# Changelog

## [0.1.1](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/compare/sam_event_mesh_tool-0.1.0...sam_event_mesh_tool-0.1.1) (2026-02-27)


### Features

* add context_expression support for sourcing parameters from a2a_context ([2572514](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/2572514d1c8a9e4d12b3b1524fbc89a3bfd4c28b))
* add control for responder reply behavior in fire-and-forget tests ([4d8c64c](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/4d8c64c770307f4b332961f596bc9c0a98f034ba))
* add fail-fast validation for required event mesh configuration ([4fa8a22](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/4fa8a22af5b255df85d64c31117e04ff2220fe2d))
* add multiple handler instances for concurrent testing ([67cbebd](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/67cbebd62d061efdd1f976ed8362b43623b44329))
* add parameter validation with fail-fast error handling ([3f8691a](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/3f8691ada5a90c977ba9a6750dcc91678db34e09))
* add pyyaml dependency and fix SolaceAiConnector initialization ([4a81001](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/4a8100167899a11c6e5d9335ec275e58b355fe5b))
* add test configuration files for EventMeshTool integration tests ([8943ac2](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/8943ac23d885a0c6888af9afb9f6bb0fe1adacbe))
* add test infrastructure with pytest dependencies and package structure ([696cf15](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/696cf154b9df91d056f11fc31ccb6ee18a32eec4))
* add topic validation to prevent empty topic errors ([4075504](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/4075504847fdfac3b38afd7075ff3dafcccbf87a))
* create scaffolding for sam-event-mesh-tool plugin ([7cc19a3](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/7cc19a3340c27c331e4543aac961e40c9f542ad8))
* **DATAGO-111686:** Add sam-event-mesh-tool plugin ([468a5de](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/468a5de066b665d4ccd489e4388715fd0772222d))
* **DATAGO-111686:** Added sam-event-mesh-tool plugin ([468a5de](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/468a5de066b665d4ccd489e4388715fd0772222d))
* **DATAGO-113851:** add SAM Ruleset Lookup Tool and Nuclia RAG Tool with documentation ([#67](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/67)) ([e254914](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/e254914368962a1704edaf9fcc32008233e8d11b))
* **DATAGO-115000:** add FOSSA SCA scanning for monorepo plugins ([#79](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/issues/79)) ([9b15f00](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/9b15f0078be038ec459dc508cfb0684a7c5c297e))
* implement core test fixtures for event mesh tool integration tests ([0f7ea6b](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/0f7ea6b0aa5512586aea439167650c7559152577))
* implement EventMeshTool class with request-response functionality ([d49b1c8](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/d49b1c8e6c7e95e2690512080c66c1d846cd7fe4))
* implement test_concurrent_requests_with_correlation for concurrency testing ([c908e7e](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/c908e7e0cd5a404d97b172158958251d1468b1d7))


### Bug Fixes

* access components through component_groups in flow structure ([7899251](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/789925159672018a93e2e3c2b705f0180fd09331))
* add dummy broker config values to satisfy validation in dev_mode ([ff73fb2](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/ff73fb200c963dbfb96cf55a0554f87948e74e0a))
* add missing boolean argument to get_data_value for context expression parsing ([02d3bde](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/02d3bde5786a3e888132e3d42d920e882f1aa3a7))
* add missing Message import to resolve undefined name error ([b64c72e](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/b64c72eae98a0901873ea7627035b91780d67099))
* add required agent_card fields to test configuration ([2f75191](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/2f75191999f0c72911c09424cbe1099245e89a7c))
* add required interval_seconds field to agent_card_publishing config ([4289246](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/42892467c547b2e743eecb98379cf5e18ddb1e38))
* add session attribute to MockInvocationContext for ToolContext ([054ca8c](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/054ca8c49dc806db26aa4d9b8623ac38b712191c))
* bump up solace_agent_mesh version to 1.4.7 ([cfdd96d](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/cfdd96d5891474a468d7631d2d42ac21e179aeb8))
* correct tool access path in integration test ([0d8eaab](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/0d8eaabaa9dffe6de7fe99fa18ad2ed0727792b8))
* correct ToolContext parameter name from _invocation_context to invocation_context ([df94098](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/df9409834f53d7b0f1f176934de7410d59874db4))
* **DATAGO-112455:** pin dependency version ([9edcd9c](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/9edcd9c22648042dc461ee2e5c9f37311b34711c))
* move multi_session_request_response config to app_config level ([925ab0d](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/925ab0dd8997c5021f92f07674b79cb55b5c9837))
* pin dependencies for sam-event-mesh-tool ([f03b38f](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/f03b38f222d5e91cb3ce23d250d8c33c36a0767e))
* prevent test isolation issue by providing instructions for all concurrent requests ([9db661c](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/9db661c34150668fde8a1b008e8cb6213024b131))
* prevent test isolation issue in test_request_timeout by providing responder instruction ([0355a04](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/0355a04df7d2dff4ed205e980479182085772189))
* resolve test isolation issue by providing control queue instructions for all requests ([6440efa](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/6440efa493cc217507eb0db6c12c40dfffbe3d6c))
* restructure agent config to use simplified component mode instead of flows ([6092b12](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/6092b12624ee16258c422798e0ea2096b0b173f6))
* update responder config to use wildcard topic subscription ([fa7d320](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/fa7d320b3508f3422406072ce67beea1864bfd1b))
* Workaround the requirements for calling SAC get_data_value ([4bf9e3d](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/4bf9e3dc09a041bcefa71146e8e3b81973bc61e0))


### Documentation

* add comprehensive implementation plan for test environment ([a1de2ce](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/a1de2ce6c9134151b0438812264fa18e11773142))
* add comprehensive README and example config for event mesh tool ([09b89fa](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/09b89faa069a54d47ba3f213e6868d93ab4ed9fd))
* add comprehensive test environment design for sam-event-mesh-tool ([12377a7](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/12377a74342bb3350b00eb35f362ef948b3b3a37))
* add detailed design for event mesh tool plugin ([0499b1c](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/0499b1c3728f6ff17426e107d4bba09f4737bbdd))
* add feature proposal for event mesh tool plugin ([7905cd3](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/7905cd3a3149a3268e43961481bd82d2932d4dd9))
* add implementation checklist for event mesh tool refactoring ([eb6a5d3](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/eb6a5d333bc5a940761f705f299f29674dbd75ca))
* add implementation checklist for test environment refactoring ([a1735f3](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/a1735f3034e9193ceb2f723e5d3a390b3cb277bf))
* add implementation plan for sam-event-mesh-tool plugin ([cf8a54f](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/cf8a54f0da263d2f98e43eb5273b199377c78f35))
* add test framework design documentation to tests directory ([6914ef7](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/6914ef78cd66cdcc7155a2bbd65f82655f4a591e))
* create comprehensive test implementation plan for event mesh tool ([8406509](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/840650990a9cde0ffee33638aad516f0db6e34f2))
* expand event-mesh-config parameters list in README ([70a55e9](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/70a55e9748916f2d4cefde4c46c32de3e75b7ba8))
* number all tests in implementation checklist for tracking ([ea0128f](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/ea0128f80c1e7dc0e589f328d9cf9582841acd70))
* update installation instructions for event mesh tool ([310e708](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins/commit/310e70880a088471ab808a4d8b3ceb3f6083e9d0))
