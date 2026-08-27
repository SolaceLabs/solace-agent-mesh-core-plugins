> [!WARNING]
> ## Solace Agent Mesh plugins in Python are now deprecated
>
> 👋 Thank you to everyone who's used the Solace Agent Mesh plugins! This Python version is now **deprecated** — it's no longer under active development and won't receive new features, bug fixes or security updates.
>
> 🚀 **Check out the new version of Solace Agent Mesh** → https://docs.solace.com/Agent-Mesh/agent-mesh.htm
>
> 🖥️ A free edition of the Solace Agent Mesh desktop app is available: https://solace.com/products/agent-mesh/download/
>
> These packages remain installable; the repository will be archived (read-only) for reference.

# SAM Ruleset Lookup Tool

## About Solace Agent Mesh

Solace Agent Mesh (SAM) is an open-source framework for building event-driven, multi-agent AI systems where specialized agents collaborate on complex tasks. It provides a standardized way for agents to communicate, share data, and integrate with external systems while keeping components loosely coupled and production-ready.

SAM helps you:

- Build event-driven multi-agent systems on Solace Event Mesh
- Connect agents, tools, gateways, and services through a common runtime
- Extend projects with installable plugins such as `sam-ruleset-lookup-tool`

Learn more in the [Solace Agent Mesh documentation](https://solacelabs.github.io/solace-agent-mesh/) and the [main project repository](https://github.com/SolaceLabs/solace-agent-mesh).

`sam-ruleset-lookup-tool` is a configuration-driven tool that provides text-based rulesets to LLM agents for reasoning. Use it when agents need shared, versioned rule text (for example policy or style guides) loaded from configuration.

## Installation

To install, run the following command

```
sam plugin install sam-ruleset-lookup-tool
```

This will create a new component configuration at `configs/plugins/<your-new-component-name-kebab-case>.yaml`.