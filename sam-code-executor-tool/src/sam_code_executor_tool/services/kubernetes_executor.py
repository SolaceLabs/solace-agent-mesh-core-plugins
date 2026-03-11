"""Kubernetes Job-based code executor implementation."""

import logging
import uuid
from typing import Optional

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.exceptions import ApiException
from kubernetes.watch import Watch

from .executor_base import BaseCodeExecutor
from .execution_models import (
    CodeExecutionInput,
    CodeExecutionResult,
    KubernetesExecutorConfig,
)

log = logging.getLogger(__name__)


class KubernetesCodeExecutor(BaseCodeExecutor):
    """
    Code executor that runs Python code in Kubernetes Jobs.

    Each code execution creates a new Job with a ConfigMap containing the code.
    The Job is automatically cleaned up via TTL after completion.

    Key Features:
    - Ephemeral, per-execution environments using Kubernetes Jobs
    - Secure-by-default Pod configuration (non-root, no privileges)
    - Optional gVisor sandboxing for enhanced security
    - Automatic garbage collection via TTL
    - InitContainer support for startup scripts
    """

    def __init__(self, config: KubernetesExecutorConfig):
        super().__init__(config)
        self._batch_v1: Optional[k8s_client.BatchV1Api] = None
        self._core_v1: Optional[k8s_client.CoreV1Api] = None

    def initialize(self) -> None:
        """
        Initialize Kubernetes API clients.

        Auth methods (in order):
        1. Explicit kubeconfig path + context
        2. In-cluster service account (when running in K8s)
        3. Default local kubeconfig (~/.kube/config)
        """
        log_identifier = "[KubernetesCodeExecutor:initialize]"
        log.info("%s Initializing Kubernetes API clients...", log_identifier)

        try:
            if self.config.kubeconfig_path:
                log.info(
                    "%s Using explicit kubeconfig from '%s'",
                    log_identifier,
                    self.config.kubeconfig_path,
                )
                k8s_config.load_kube_config(
                    config_file=self.config.kubeconfig_path,
                    context=self.config.kubeconfig_context,
                )
            else:
                try:
                    k8s_config.load_incluster_config()
                    log.info(
                        "%s Using in-cluster Kubernetes configuration", log_identifier
                    )
                except k8s_config.ConfigException:
                    log.info(
                        "%s In-cluster config not found, falling back to default kubeconfig",
                        log_identifier,
                    )
                    k8s_config.load_kube_config()

            self._batch_v1 = k8s_client.BatchV1Api()
            self._core_v1 = k8s_client.CoreV1Api()

            # Verify API access
            self._core_v1.list_namespace(limit=1)
            log.info("%s Kubernetes API clients initialized successfully", log_identifier)

            self._initialized = True

        except k8s_config.ConfigException as e:
            raise RuntimeError(
                f"Failed to configure Kubernetes client: {e}"
            ) from e
        except ApiException as e:
            raise RuntimeError(
                f"Failed to connect to Kubernetes API: {e.reason}"
            ) from e

    def execute_code(
        self, execution_input: CodeExecutionInput, timeout_seconds: Optional[int] = None
    ) -> CodeExecutionResult:
        """
        Execute Python code via a Kubernetes Job.

        Steps:
        1. Create ConfigMap with code as code.py
        2. Create Job with container, security context, and resource limits
        3. Set Job as owner of ConfigMap (cascade delete)
        4. Watch Job completion
        5. Get pod logs as stdout/stderr
        """
        log_identifier = "[KubernetesCodeExecutor:execute]"

        if not self._initialized or not self._batch_v1:
            return CodeExecutionResult(
                success=False, error_message="Executor not initialized", exit_code=-1
            )

        execution_id = execution_input.execution_id or uuid.uuid4().hex
        job_name = f"sam-exec-{uuid.uuid4().hex[:10]}"
        configmap_name = f"code-src-{job_name}"
        timeout = timeout_seconds or execution_input.timeout_seconds or 300

        log.debug("%s Starting execution %s (job=%s)", log_identifier, execution_id, job_name)

        try:
            # Create ConfigMap with code
            self._create_code_configmap(configmap_name, execution_input.code)

            # Create Job
            job_manifest = self._create_job_manifest(job_name, configmap_name)
            created_job = self._batch_v1.create_namespaced_job(
                body=job_manifest, namespace=self.config.namespace
            )

            # Set Job as owner of ConfigMap for cascade delete
            self._add_owner_reference(created_job, configmap_name)

            log.info(
                "%s Submitted Job '%s' to namespace '%s'",
                log_identifier,
                job_name,
                self.config.namespace,
            )

            # Watch for completion
            result = self._watch_job_completion(job_name, timeout)
            result.execution_id = execution_id
            return result

        except ApiException as e:
            log.error(
                "%s Kubernetes API error during job '%s': %s",
                log_identifier,
                job_name,
                e.reason,
            )
            return CodeExecutionResult(
                success=False,
                error_message=f"Kubernetes API error: {e.reason}",
                exit_code=-1,
                execution_id=execution_id,
            )
        except TimeoutError as e:
            log.error("%s Job timed out: %s", log_identifier, e)
            logs = self._get_pod_logs(job_name)
            return CodeExecutionResult(
                success=False,
                error_message=f"Execution timed out: {e}",
                stdout=logs,
                exit_code=-1,
                execution_id=execution_id,
            )
        except Exception as e:
            log.exception("%s Unexpected error during job '%s': %s", log_identifier, job_name, e)
            return CodeExecutionResult(
                success=False,
                error_message=f"Unexpected error: {e}",
                exit_code=-1,
                execution_id=execution_id,
            )

    def cleanup(self) -> None:
        """No-op for Kubernetes - TTL handles cleanup."""
        log_identifier = "[KubernetesCodeExecutor:cleanup]"
        log.info("%s Cleanup called (no-op, TTL handles Job cleanup)", log_identifier)
        self._initialized = False

    def is_healthy(self) -> bool:
        """Check if Kubernetes API is reachable."""
        if not self._initialized or not self._core_v1:
            return False

        try:
            self._core_v1.list_namespace(limit=1)
            return True
        except Exception:
            return False

    def _create_code_configmap(self, name: str, code: str) -> None:
        """Create a ConfigMap to hold the Python code."""
        log_identifier = "[KubernetesCodeExecutor:create_configmap]"

        body = k8s_client.V1ConfigMap(
            metadata=k8s_client.V1ObjectMeta(name=name),
            data={"code.py": code},
        )

        self._core_v1.create_namespaced_config_map(
            namespace=self.config.namespace, body=body
        )
        log.debug("%s Created ConfigMap '%s'", log_identifier, name)

    def _create_job_manifest(
        self, job_name: str, configmap_name: str
    ) -> k8s_client.V1Job:
        """Create the Job manifest with security best practices."""

        # Security context for containers
        security_context = k8s_client.V1SecurityContext(
            run_as_non_root=self.config.run_as_non_root,
            run_as_user=self.config.run_as_user,
            allow_privilege_escalation=False,
            read_only_root_filesystem=self.config.read_only_root_filesystem,
            capabilities=k8s_client.V1Capabilities(drop=["ALL"]),
        )

        # Resource requirements
        resources = k8s_client.V1ResourceRequirements(
            requests={
                "cpu": self.config.cpu_requested,
                "memory": self.config.memory_requested,
            },
            limits={
                "cpu": self.config.cpu_limit,
                "memory": self.config.memory_limit,
            },
        )

        # Volume mounts
        code_volume_mount = k8s_client.V1VolumeMount(
            name="code-volume", mount_path="/app", read_only=True
        )

        # Main container
        main_container = k8s_client.V1Container(
            name="code-runner",
            image=self.config.image,
            command=["python3", "/app/code.py"],
            volume_mounts=[code_volume_mount],
            security_context=security_context,
            resources=resources,
            env=[
                k8s_client.V1EnvVar(name=k, value=v)
                for k, v in self.config.environment.items()
            ] if self.config.environment else None,
        )

        # Volumes
        volumes = [
            k8s_client.V1Volume(
                name="code-volume",
                config_map=k8s_client.V1ConfigMapVolumeSource(name=configmap_name),
            )
        ]

        # InitContainers for startup script
        init_containers = None
        if self.config.startup_command.enabled and self.config.startup_command.script:
            # Add shared volume for InitContainer to write to
            shared_volume = k8s_client.V1Volume(
                name="shared-data",
                empty_dir=k8s_client.V1EmptyDirVolumeSource(),
            )
            volumes.append(shared_volume)

            shared_volume_mount = k8s_client.V1VolumeMount(
                name="shared-data", mount_path="/workspace"
            )

            # Add shared volume to main container
            main_container.volume_mounts.append(shared_volume_mount)

            # Determine command based on script type
            script = self.config.startup_command.script
            if self.config.startup_command.script_type == "python":
                init_command = ["python3", "-c", script]
            else:  # shell
                init_command = ["/bin/sh", "-c", script]

            init_container = k8s_client.V1Container(
                name="setup",
                image=self.config.image,
                command=init_command,
                volume_mounts=[shared_volume_mount],
                # InitContainer needs writable filesystem for pip install etc.
                security_context=k8s_client.V1SecurityContext(
                    run_as_non_root=self.config.run_as_non_root,
                    run_as_user=self.config.run_as_user,
                    allow_privilege_escalation=False,
                    # InitContainer may need writable filesystem
                    read_only_root_filesystem=False,
                    capabilities=k8s_client.V1Capabilities(drop=["ALL"]),
                ),
                resources=resources,
                env=[
                    k8s_client.V1EnvVar(name=k, value=v)
                    for k, v in self.config.environment.items()
                ] if self.config.environment else None,
            )
            init_containers = [init_container]

        # Pod spec
        pod_spec_kwargs = {
            "restart_policy": "Never",
            "containers": [main_container],
            "volumes": volumes,
        }

        if init_containers:
            pod_spec_kwargs["init_containers"] = init_containers

        # Add gVisor runtime if enabled
        if self.config.use_gvisor:
            pod_spec_kwargs["runtime_class_name"] = "gvisor"
            pod_spec_kwargs["tolerations"] = [
                k8s_client.V1Toleration(
                    key="sandbox.gke.io/runtime",
                    operator="Equal",
                    value="gvisor",
                    effect="NoSchedule",
                )
            ]

        pod_spec = k8s_client.V1PodSpec(**pod_spec_kwargs)

        # Job spec
        job_spec = k8s_client.V1JobSpec(
            template=k8s_client.V1PodTemplateSpec(spec=pod_spec),
            backoff_limit=0,  # Do not retry on failure
            ttl_seconds_after_finished=self.config.ttl_seconds_after_finished,
        )

        return k8s_client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=k8s_client.V1ObjectMeta(name=job_name),
            spec=job_spec,
        )

    def _add_owner_reference(
        self, owner_job: k8s_client.V1Job, configmap_name: str
    ) -> None:
        """Set Job as owner of ConfigMap for automatic cascade delete."""
        log_identifier = "[KubernetesCodeExecutor:add_owner_ref]"

        owner_reference = k8s_client.V1OwnerReference(
            api_version=owner_job.api_version,
            kind=owner_job.kind,
            name=owner_job.metadata.name,
            uid=owner_job.metadata.uid,
            controller=True,
        )

        patch_body = {"metadata": {"ownerReferences": [owner_reference.to_dict()]}}

        try:
            self._core_v1.patch_namespaced_config_map(
                name=configmap_name,
                namespace=self.config.namespace,
                body=patch_body,
            )
            log.debug(
                "%s Set Job '%s' as owner of ConfigMap '%s'",
                log_identifier,
                owner_job.metadata.name,
                configmap_name,
            )
        except ApiException as e:
            log.warning(
                "%s Failed to set ownerReference on ConfigMap '%s': %s",
                log_identifier,
                configmap_name,
                e.reason,
            )

    def _watch_job_completion(
        self, job_name: str, timeout_seconds: int
    ) -> CodeExecutionResult:
        """Watch Job completion using the Kubernetes watch API."""
        log_identifier = "[KubernetesCodeExecutor:watch]"

        watch = Watch()
        try:
            for event in watch.stream(
                self._batch_v1.list_namespaced_job,
                namespace=self.config.namespace,
                field_selector=f"metadata.name={job_name}",
                timeout_seconds=timeout_seconds,
            ):
                job = event["object"]

                if job.status.succeeded:
                    watch.stop()
                    log.info("%s Job '%s' succeeded", log_identifier, job_name)
                    logs = self._get_pod_logs(job_name)
                    return CodeExecutionResult(
                        success=True,
                        stdout=logs,
                        exit_code=0,
                    )

                if job.status.failed:
                    watch.stop()
                    log.error("%s Job '%s' failed", log_identifier, job_name)
                    logs = self._get_pod_logs(job_name)
                    return CodeExecutionResult(
                        success=False,
                        stderr=logs,
                        error_message="Job failed",
                        exit_code=1,
                    )

            # Watch timed out
            raise TimeoutError(
                f"Job '{job_name}' did not complete within {timeout_seconds}s"
            )

        finally:
            watch.stop()

    def _get_pod_logs(self, job_name: str) -> str:
        """Retrieve logs from the Pod created by the Job."""
        log_identifier = "[KubernetesCodeExecutor:get_logs]"

        try:
            pods = self._core_v1.list_namespaced_pod(
                namespace=self.config.namespace,
                label_selector=f"job-name={job_name}",
                limit=1,
            )

            if not pods.items:
                log.warning("%s Could not find Pod for Job '%s'", log_identifier, job_name)
                return ""

            pod_name = pods.items[0].metadata.name
            logs = self._core_v1.read_namespaced_pod_log(
                name=pod_name, namespace=self.config.namespace
            )
            return logs

        except ApiException as e:
            log.error(
                "%s Failed to retrieve logs for Job '%s': %s",
                log_identifier,
                job_name,
                e.reason,
            )
            return f"[Error retrieving logs: {e.reason}]"
