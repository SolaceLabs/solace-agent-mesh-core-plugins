# Slack Gateway Adapter SAM Plugin

This plugin provides a Slack gateway adapter for the Solace Agent Mesh framework using the new generic gateway framework. It allows you to interact with Slack channels and messages, enabling bi-directional communication between Slack users and SAM agents.

## Overview

The Slack Gateway Adapter is a complete replacement for the legacy `sam-slack` plugin, built on the modern SAM gateway architecture. It provides:

- **Socket Mode Integration**: Real-time communication with Slack via WebSocket
- **Rich Message Support**: Text, files, images, and structured data
- **Thread Management**: Maintains conversation context in Slack threads
- **User Authentication**: Maps Slack users to SAM identity via email
- **Embed Resolution**: Automatically resolves and processes embedded artifacts
- **Feedback Collection**: Optional integration with feedback services

## Installation

Once the plugin is installed (e.g., from PyPI or a local wheel file):

```bash
sam plugin add <your-new-component-name> --plugin sam-slack-gateway-adapter
```

This will create a new component configuration at `configs/plugins/<your-new-component-name-kebab-case>.yaml`.

## Configuration

### Required Environment Variables

- `SLACK_BOT_TOKEN`: Your Slack Bot Token (starts with 'xoxb-')
- `SLACK_APP_TOKEN`: Your Slack App Token for Socket Mode (starts with 'xapp-')
- `NAMESPACE`: The SAM namespace for your deployment

### Slack App Setup

To use this plugin, you need to create a Slack App with the following configurations:

1. **Socket Mode**: Enable Socket Mode in your Slack App settings
2. **Bot Token Scopes**: Add the following OAuth scopes:
   - `app_mentions:read` - View messages that directly mention your app
   - `chat:write` - Send messages as the app
   - `files:read` - View files shared in channels and conversations
   - `files:write` - Upload, edit, and delete files as the app
   - `channels:history` - View messages and other content in public channels
   - `groups:history` - View messages and other content in private channels
   - `im:history` - View messages and other content in direct messages
   - `mpim:history` - View messages and other content in group direct messages
   - `users:read` - View people in the workspace
   - `users:read.email` - View email addresses of people in the workspace

3. **Event Subscriptions**: Subscribe to the following bot events:
   - `app_mention` - When your app is mentioned in a channel
   - `message.channels` - Messages in public channels
   - `message.groups` - Messages in private channels
   - `message.im` - Direct messages to your app
   - `message.mpim` - Group direct messages

### Configuration Options

The main configuration options in your component YAML file:

```yaml
app_config:
  # Gateway Configuration
  namespace: "${NAMESPACE}"
  gateway_id: my-slack-gateway-01  # Auto-generated if omitted
  default_agent_name: "OrchestratorAgent"  # Agent to use if no mention specifies one

  # Slack Adapter-Specific Config
  adapter_config:
    slack_bot_token: ${SLACK_BOT_TOKEN}
    slack_app_token: ${SLACK_APP_TOKEN}
    slack_initial_status_message: ":thinking_face: Thinking..."  # Set empty "" to disable
    correct_markdown_formatting: true
    slack_email_cache_ttl_seconds: 3600  # Cache user email lookups for 1 hour
    feedback_enabled: false  # Enable to show thumbs up/down feedback buttons

  # Embed Resolution
  enable_embed_resolution: true
  gateway_artifact_content_limit_bytes: 10000000  # 10MB
  gateway_recursive_embed_depth: 3

  # Authorization
  authorization_service:
    type: "none"  # Or "default_rbac"
```

## Usage

### Interacting with the Gateway

Once deployed, users can interact with your SAM agents via Slack:

1. **Direct Mention**: `@YourBot what is the weather today?`
2. **Direct Message**: Send a DM to your bot
3. **Thread Replies**: Continue conversations in threads

### Agent Selection

- **Default Agent**: Messages without a specific agent mention use `default_agent_name`
- **Specific Agent**: Mention an agent by name: `@YourBot @WeatherAgent what's the forecast?`

### File Attachments

The adapter automatically processes files attached to Slack messages and makes them available to agents as artifacts.

## Features

### Message Queue Management

The adapter includes intelligent message queue management to:
- Handle rate limits gracefully
- Batch status updates efficiently
- Prevent duplicate messages
- Manage thread contexts

### Markdown Formatting

Slack markdown differs from standard markdown. The adapter can automatically convert:
- Code blocks and inline code
- Bold and italic text
- Lists and formatting
- Links and mentions

Set `correct_markdown_formatting: true` to enable automatic conversion.

### User Feedback Collection

The adapter supports optional thumbs up/down feedback collection on task completions:

1. **Enable in adapter config**:
   ```yaml
   adapter_config:
     feedback_enabled: true
   ```

2. **Configure feedback publishing** (optional - if you want to send feedback to an external service):
   ```yaml
   feedback_publishing:
     enabled: true
     feedback_post_url: "http://your-feedback-service.example.com/feedback"
     feedback_post_headers:
       Authorization: "Bearer your_feedback_token"
       Content-Type: "application/json"
   ```

When enabled, users will see thumbs up/down buttons after task completion. They can optionally provide text comments. Feedback is submitted via the SAM feedback mechanism.

### Error Handling

Errors are gracefully reported back to users in Slack with helpful messages and context.

## Development

### Running Tests

```bash
hatch test
```

### Building the Package

```bash
hatch build
```

## Architecture

This plugin is built on the SAM Generic Gateway Framework and implements the `GatewayAdapter` interface. It handles:

- **Inbound**: Slack events → SAM tasks
- **Outbound**: SAM updates → Slack messages
- **State Management**: Thread tracking and user context
- **Identity**: User email mapping for authentication

## Troubleshooting

### Bot doesn't respond to messages

- Verify `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` are set correctly
- Check that Socket Mode is enabled in your Slack App
- Ensure your bot has been invited to the channel
- Review logs for connection errors

### User identity issues

- Verify the bot has `users:read.email` scope
- Check that users have email addresses associated with their Slack accounts
- Review `slack_email_cache_ttl_seconds` setting

### Rate limiting

- The adapter includes built-in rate limit handling
- Consider adjusting message batch sizes if hitting limits frequently

## License

See the LICENSE file in the root of the repository.
