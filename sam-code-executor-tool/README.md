# SAM Code Executor Tool

A Solace Agent Mesh plugin that provides sandboxed Python code execution using Docker containers or Kubernetes Jobs.

## Features

- **Sandboxed Execution**: Code runs in isolated Docker containers or Kubernetes Jobs
- **Lifecycle Management**: Containers/Jobs are managed automatically
- **Startup Scripts**: Optional inline Python or shell scripts run on initialization
- **Environment Variables**: Pass environment variables from host to execution environment
- **Artifact Integration**: Save execution outputs as SAM artifacts
- **Health Monitoring**: Graceful degradation when executor is unavailable
- **Kubernetes Support**: Run code in ephemeral K8s Jobs with optional gVisor sandboxing

## Installation

```bash
pip install sam-code-executor-tool
```

## Executor Types

| Type | Description | Use Case |
|------|-------------|----------|
| `docker` | Persistent container, reused across executions | Local development, single-node deployments |
| `kubernetes` | Ephemeral Jobs, one per execution | Production, multi-tenant, enhanced security |

---

## Docker Configuration

### Basic Configuration

```yaml
tools:
  - tool_type: python
    component_module: "sam_code_executor_tool.tools"
    class_name: "CodeExecutorTool"
    tool_config:
      tool_name: "execute_python"
      tool_description: "Execute Python code in a sandboxed environment"
      executor_type: "docker"
      default_timeout_seconds: 30
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

### Docker with Startup Script

```yaml
docker:
  image: "python:3.11-slim"
  memory_limit: "1g"
  network_disabled: false  # Required for pip install
  startup_command:
    enabled: true
    script_type: "shell"
    script: |
      pip install numpy pandas matplotlib
      echo "Setup complete"
    timeout_seconds: 300
```

### Docker Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `image` | string | "python:3.11-slim" | Docker image to use |
| `working_directory` | string | "/workspace" | Working directory in container |
| `memory_limit` | string | "512m" | Memory limit (e.g., "512m", "1g") |
| `cpu_limit` | float | 1.0 | CPU limit (1.0 = one full CPU) |
| `network_disabled` | bool | true | Disable network access |
| `environment` | dict | {} | Environment variables |
| `volumes` | dict | {} | Volume mounts |

---

## Kubernetes Configuration

### Basic Configuration

```yaml
tools:
  - tool_type: python
    component_module: "sam_code_executor_tool.tools"
    class_name: "CodeExecutorTool"
    tool_config:
      tool_name: "execute_python_k8s"
      tool_description: "Execute Python in a Kubernetes sandbox"
      executor_type: "kubernetes"
      default_timeout_seconds: 60
      kubernetes:
        namespace: "code-execution"
        kubeconfig_path: "${KUBECONFIG}"  # Or omit for in-cluster auth
        image: "python:3.11-slim"
        cpu_requested: "200m"
        cpu_limit: "500m"
        memory_requested: "256Mi"
        memory_limit: "512Mi"
        use_gvisor: false
        run_as_user: 1001
        run_as_non_root: true
        ttl_seconds_after_finished: 300
```

### Kubernetes with Startup Script (InitContainer)

```yaml
kubernetes:
  namespace: "code-execution"
  image: "python:3.11-slim"
  memory_limit: "1Gi"
  use_gvisor: true
  startup_command:
    enabled: true
    script_type: "shell"
    script: |
      pip install numpy pandas matplotlib
      echo "Packages installed"
    timeout_seconds: 120
```

### Kubernetes Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `kubeconfig_path` | string | null | Path to kubeconfig (uses default/in-cluster if not set) |
| `kubeconfig_context` | string | null | Kubernetes context to use |
| `namespace` | string | "default" | Kubernetes namespace for Jobs |
| `image` | string | "python:3.11-slim" | Docker image to use |
| `cpu_requested` | string | "200m" | CPU request |
| `cpu_limit` | string | "500m" | CPU limit |
| `memory_requested` | string | "256Mi" | Memory request |
| `memory_limit` | string | "512Mi" | Memory limit |
| `use_gvisor` | bool | false | Use gVisor runtime (requires GKE) |
| `run_as_user` | int | 1001 | User ID for container |
| `run_as_non_root` | bool | true | Enforce non-root execution |
| `read_only_root_filesystem` | bool | true | Read-only root filesystem |
| `ttl_seconds_after_finished` | int | 600 | Seconds to keep completed Jobs |
| `environment` | dict | {} | Environment variables |

### RBAC Requirements

The executor needs a ServiceAccount with these permissions:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: code-executor-role
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["create", "delete", "get", "patch"]
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["create", "delete", "get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods", "pods/log"]
    verbs: ["get", "list"]
```

---

## Tool Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `tool_name` | string | required | Name of the tool for LLM invocation |
| `tool_description` | string | "Execute Python code..." | Description shown to LLM |
| `executor_type` | string | "docker" | Executor backend: "docker" or "kubernetes" |
| `default_timeout_seconds` | int | 30 | Default execution timeout |
| `max_output_size` | int | 1048576 | Maximum output size in bytes |

## Startup Command Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | false | Enable startup script |
| `script_type` | string | "shell" | Script type: "python" or "shell" |
| `script` | string | "" | Inline script content |
| `timeout_seconds` | int | 300 | Startup script timeout |

---

## Tool Parameters

When the LLM invokes the tool, it can pass these parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | yes | Python code to execute |
| `timeout_seconds` | int | no | Execution timeout override |
| `save_output_as_artifact` | bool | no | Save output as artifact |
| `output_filename` | string | no | Filename for artifact |

---

## Examples

### Git Clone in Startup (Docker)

```yaml
docker:
  network_disabled: false
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

    subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas", "numpy"])

    data_url = os.environ.get("DATA_SOURCE_URL")
    if data_url:
        import requests
        resp = requests.get(data_url)
        with open("/workspace/data.json", "wb") as f:
            f.write(resp.content)

    print("Environment ready")
  timeout_seconds: 300
```

---

## Security

### Docker Security
- **Network Disabled**: Containers cannot make network requests (default)
- **Resource Limits**: Memory and CPU constraints
- **Execution Timeout**: Prevents infinite loops

### Kubernetes Security
- **Ephemeral Jobs**: Each execution is isolated
- **Non-root Execution**: `run_as_user: 1001`
- **Drop All Capabilities**: Minimal container permissions
- **Read-only Filesystem**: Prevents persistence
- **gVisor Sandboxing**: Optional kernel-level isolation (GKE)
- **TTL Auto-cleanup**: Jobs are automatically removed

---

## Requirements

### Docker Executor
- Docker installed and running
- User must have Docker permissions

### Kubernetes Executor
- Kubernetes cluster access (kubeconfig or in-cluster)
- ServiceAccount with required RBAC permissions
- Optional: gVisor-enabled node pool for `use_gvisor: true`

## License

Apache License 2.0
