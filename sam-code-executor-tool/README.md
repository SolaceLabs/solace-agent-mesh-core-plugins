# SAM Code Executor Tool

A Solace Agent Mesh plugin that provides sandboxed Python code execution using Docker containers.

## Features

- **Sandboxed Execution**: Code runs in isolated Docker containers
- **Lifecycle Management**: Containers are created on init and cleaned up automatically
- **Startup Scripts**: Optional inline Python or shell scripts run on container initialization
- **Environment Variables**: Pass environment variables from host to container
- **Artifact Integration**: Save execution outputs as SAM artifacts
- **Health Monitoring**: Graceful degradation when executor is unavailable

## Installation

```bash
pip install sam-code-executor-tool
```

## Configuration

### Basic Configuration

```yaml
tools:
  - tool_type: python
    component_module: "sam_code_executor_tool.tools"
    component_base_path: .
    class_name: "CodeExecutorTool"
    tool_config:
      tool_name: "execute_python"
      tool_description: "Execute Python code in a sandboxed environment"
      executor_type: "docker"
      default_timeout_seconds: 30
      max_output_size: 1048576
      docker:
        image: "python:3.11-slim"
        working_directory: "/workspace"
        memory_limit: "512m"
        cpu_limit: 1.0
        network_disabled: true
        environment:
          PYTHONDONTWRITEBYTECODE: "1"
        startup_command:
          enabled: false
```

### Configuration with Startup Script

```yaml
tools:
  - tool_type: python
    component_module: "sam_code_executor_tool.tools"
    component_base_path: .
    class_name: "CodeExecutorTool"
    tool_config:
      tool_name: "execute_python_with_packages"
      tool_description: "Execute Python with pre-installed packages"
      executor_type: "docker"
      default_timeout_seconds: 60
      docker:
        image: "python:3.11-slim"
        memory_limit: "1g"
        cpu_limit: 2.0
        network_disabled: false  # Required for pip install
        environment:
          PYTHONDONTWRITEBYTECODE: "1"
          GIT_REPO_URL: "${GIT_REPO_URL}"
        startup_command:
          enabled: true
          script_type: "shell"  # or "python"
          script: |
            apt-get update && apt-get install -y git
            pip install numpy pandas matplotlib
            if [ -n "$GIT_REPO_URL" ]; then
              git clone "$GIT_REPO_URL" /workspace/repo
            fi
            echo "Setup complete"
          timeout_seconds: 300
```

## Configuration Options

### Tool Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `tool_name` | string | required | Name of the tool for LLM invocation |
| `tool_description` | string | "Execute Python code..." | Description shown to LLM |
| `executor_type` | string | "docker" | Executor backend (currently only "docker") |
| `default_timeout_seconds` | int | 30 | Default execution timeout |
| `max_output_size` | int | 1048576 | Maximum output size in bytes |

### Docker Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `image` | string | "python:3.11-slim" | Docker image to use |
| `working_directory` | string | "/workspace" | Working directory in container |
| `memory_limit` | string | "512m" | Memory limit (e.g., "512m", "1g") |
| `cpu_limit` | float | 1.0 | CPU limit (1.0 = one full CPU) |
| `network_disabled` | bool | true | Disable network access |
| `environment` | dict | {} | Environment variables |
| `volumes` | dict | {} | Volume mounts |

### Startup Command Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | false | Enable startup script |
| `script_type` | string | "shell" | Script type: "python" or "shell" |
| `script` | string | "" | Inline script content |
| `timeout_seconds` | int | 300 | Startup script timeout |

## Tool Parameters

When the LLM invokes the tool, it can pass these parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | yes | Python code to execute |
| `timeout_seconds` | int | no | Execution timeout override |
| `save_output_as_artifact` | bool | no | Save output as artifact |
| `output_filename` | string | no | Filename for artifact |

## Environment Variables

Environment variables can be passed to the container from the host:

```yaml
docker:
  environment:
    MY_API_KEY: "${MY_API_KEY}"      # From host environment
    GIT_REPO_URL: "${GIT_REPO_URL}"  # From host environment
    STATIC_VAR: "some_value"         # Static value
```

These are available in:
- Startup scripts: `$MY_API_KEY` (shell) or `os.environ["MY_API_KEY"]` (Python)
- All code executions

## Examples

### Git Clone in Startup

```yaml
startup_command:
  enabled: true
  script_type: "shell"
  script: |
    apt-get update && apt-get install -y git
    git clone "$GIT_REPO_URL" /workspace/repo
    pip install -r /workspace/repo/requirements.txt
  timeout_seconds: 600
```

### Python Setup Script

```yaml
startup_command:
  enabled: true
  script_type: "python"
  script: |
    import subprocess
    import sys
    import os

    # Install packages
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas", "numpy"])

    # Download data
    data_url = os.environ.get("DATA_SOURCE_URL")
    if data_url:
        import requests
        resp = requests.get(data_url)
        with open("/workspace/data.json", "wb") as f:
            f.write(resp.content)

    print("Environment ready")
  timeout_seconds: 300
```

## Security

By default, the executor runs with these security measures:

- **Network Disabled**: Containers cannot make network requests (set `network_disabled: false` to enable)
- **Resource Limits**: Memory and CPU constraints prevent resource exhaustion
- **Execution Timeout**: Prevents infinite loops
- **Output Size Limits**: Prevents memory exhaustion from large outputs

## Requirements

- Docker must be installed and running on the host
- The user running SAM must have Docker permissions

## License

Apache License 2.0
