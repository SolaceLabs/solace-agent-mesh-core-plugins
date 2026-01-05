import subprocess
import sys
import tomllib
import logging
import tempfile
import hashlib
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

# =====================================================================
# Runtime root selection  (each DSN gets its own isolated environment)
# =====================================================================

def get_runtime_root(connection_string: str) -> Path:
    base = Path(tempfile.gettempdir()) / "sam_sql_analytics"
    digest = hashlib.sha1(connection_string.encode()).hexdigest()[:10]
    root = base / digest
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_venv_path(connection_string: str) -> Path:
    return get_runtime_root(connection_string) / "venv"


# =====================================================================
# Load subprocess dependencies from pyproject
# Works both in editable mode and installed site-packages
# =====================================================================

def load_subprocess_deps() -> list[str]:
    """
    Search upward for pyproject.toml and read:
    [tool.sam-sql-analytics.subprocess-deps.packages]
    """
    candidates = [
        Path.cwd() / "pyproject.toml",
        *[p / "pyproject.toml" for p in Path(__file__).resolve().parents],
    ]

    for path in candidates:
        if not path.exists():
            continue

        try:
            with path.open("rb") as f:
                data = tomllib.load(f)

            return data["tool"]["sam-sql-analytics"]["subprocess-deps"]["packages"]
        except Exception:
            continue

    raise RuntimeError("Could not locate subprocess deps in pyproject.toml")


# =====================================================================
# Copy runtime scripts into venv
# =====================================================================

def copy_runtime_into_venv(venv_path: Path):
    """
    Copy only the /runtime folder into the venv.
    Result:  <venv>/runtime/run_discovery.py  etc
    """
    pkg_root = Path(__file__).resolve().parents[1]
    src_runtime = pkg_root / "subprocess" / "runtime"
    dst_runtime = venv_path / "runtime"

    if dst_runtime.exists():
        shutil.rmtree(dst_runtime)

    shutil.copytree(src_runtime, dst_runtime)
    log.info("Copied runtime → %s", dst_runtime)


# =====================================================================
# Venv lifecycle
# =====================================================================

def create_venv(path: Path):
    if path.exists():
        return
    log.info("Creating venv: %s", path)
    subprocess.check_call([sys.executable, "-m", "venv", str(path)])


def install_deps(venv_path: Path, deps: list[str]):
    pip = venv_path / "bin" / "pip"

    log.info("Upgrading pip...")
    subprocess.check_call([str(pip), "install", "--upgrade", "pip", "setuptools", "wheel"])

    log.info("Installing subprocess deps: %s", deps)
    subprocess.check_call([str(pip), "install"] + deps)


# =====================================================================
# Main entry
# =====================================================================

def ensure_runtime_ready(connection_string: str) -> Path:
    venv = get_venv_path(connection_string)
    deps = load_subprocess_deps()

    create_venv(venv)

    marker = venv / ".deps_installed"

    if not marker.exists():
        install_deps(venv, deps)
        marker.touch()
        log.info("Subprocess deps installed successfully")
    else:
        log.info("Subprocess environment already prepared")

    # ---------------------------------------------------------
    # ALWAYS copy runtime AFTER installing deps
    # ---------------------------------------------------------
    copy_runtime_into_venv(venv)

    return venv


if __name__ == "__main__":
    ensure_runtime_ready("postgresql://demo")
