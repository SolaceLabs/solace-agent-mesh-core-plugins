# Slack SAM Plugin

> **⚠️ DEPRECATED**: This plugin is deprecated and will be removed in a future version.
>
> **Please migrate to [sam-slack-gateway-adapter](../sam-slack-gateway-adapter/)** which uses the new gateway adapter framework.
>
> The new adapter provides:
> - Improved architecture built on the generic gateway framework
> - Better performance with message queue management
> - Enhanced error handling and recovery
> - Simplified configuration
> - Active development and support
>
> See the [Migration Guide](#migration-guide) below.

This plugin allows you to interact with Slack channels and messages through the Solace Agent Mesh framework. It provides a way to send and receive messages and handle events from Slack.

## Installation

Once the plugin is installed (e.g., from PyPI or a local wheel file):
```bash
sam plugin add <your-new-component-name> --plugin sam-slack
```
This will create a new component configuration at `configs/plugins/<your-new-component-name-kebab-case>.yaml`.