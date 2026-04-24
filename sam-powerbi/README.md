# SamPowerbi SAM Plugin

PowerBI executeQueries tool with MSAL device-code delegated auth

This is a plugin for Solace Agent Mesh (SAM).

## About Solace Agent Mesh

Solace Agent Mesh (SAM) is an open-source framework for building event-driven, multi-agent AI systems where specialized agents collaborate on complex tasks. It provides a standardized way for agents to communicate, share data, and integrate with external systems while keeping components loosely coupled and production-ready.

SAM helps you:

- Build event-driven multi-agent systems on Solace Event Mesh
- Connect agents, tools, gateways, and services through a common runtime
- Extend projects with installable plugins such as `sam-nuclia-tool`

Learn more in the [Solace Agent Mesh documentation](https://solacelabs.github.io/solace-agent-mesh/) and the [main project repository](https://github.com/SolaceLabs/solace-agent-mesh).

## Features

This agent connects to Power BI via the Power BI REST API to retrieve, analyze, and summarize data from reports and datasets. 
It can execute DAX queries against published datasets, fetch report metadata, and translate natural language questions into structured queries — returning insights without requiring the user to navigate the Power BI interface directly.

- **Natural Language to DAX query:** Translate the user's question into a valid DAX query

## Configuration

### Environment Variables

Set the following environment variables for your MongoDB connection:

```bash
export AZURE_TENANT_ID="your azure tenant id"
export POWERBI_CLIENT_ID="your powerBI client id"
export POWERBI_WORKSPACE_ID="your powerBI workspace id"
export POWERBI_SEMANTIC_MODEL_ID="your semantic model id"
export POWERBI_TOKEN_CACHE="your location for your token-cahe, default /tmp/samv2/powerbi_msal_cache.json"
```

## Build

To build the PowerBI Agent plugin, run the following command:
```bash\
sam plugin build
```

## Installation

To install the PowerBI Agent plugin, run the following command:

```bash
sam plugin install sam-powerbi
```

This will create a new component configuration at `configs/plugins/<your-new-component-name-kebab-case>.yaml`.
