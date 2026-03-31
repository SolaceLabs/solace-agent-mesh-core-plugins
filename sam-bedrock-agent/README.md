# sam-bedrock-agent

`sam-bedrock-agent` is an official Solace Agent Mesh core plugin that lets you import Amazon Bedrock agents and flows into your SAM project as reusable actions.

## About Solace Agent Mesh

Solace Agent Mesh (SAM) is an open-source framework for building event-driven, multi-agent AI systems where specialized agents collaborate on complex tasks. It provides a standardized way for agents to communicate, share data, and integrate with external systems while keeping components loosely coupled and production-ready.

SAM helps you:

- Build event-driven multi-agent systems on Solace Event Mesh
- Connect agents, tools, gateways, and services through a common runtime
- Extend projects with installable plugins such as `sam-bedrock-agent`

Learn more in the [Solace Agent Mesh documentation](https://solacelabs.github.io/solace-agent-mesh/) and the [main project repository](https://github.com/SolaceLabs/solace-agent-mesh).

## What This Plugin Adds

This plugin makes it easy to bring Amazon Bedrock capabilities into Solace Agent Mesh by:

- Importing one or multiple Amazon Bedrock agents or flows
- Exposing them as actions inside your SAM project
- Generating a standard plugin configuration under `configs/plugins/`

## Quick Start

If you do not already have SAM installed, install it first:

```bash
pip install solace-agent-mesh
```

Then add the plugin from your SAM project directory:

```bash
sam plugin add <your-new-component-name> --plugin sam-bedrock-agent
```

This creates a component configuration at `configs/plugins/<your-new-component-name-kebab-case>.yaml`.

## Configuration

The generated configuration file contains two sections that require updates:

1. The section marked `# 1. UPDATE REQUIRED - START #` configures the Amazon Bedrock agent or flow and the internal agent settings.
2. The section marked `# 2. UPDATE REQUIRED - START #` configures the public-facing API that other agents use to interact with it.

## Additional Resources

- [Solace Agent Mesh Docs](https://solacelabs.github.io/solace-agent-mesh/)
- [Solace Agent Mesh Repository](https://github.com/SolaceLabs/solace-agent-mesh)
- [Core Plugins Repository](https://github.com/SolaceLabs/solace-agent-mesh-core-plugins)