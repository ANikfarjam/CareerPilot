"""
Configuration for the local Docker sandbox the agents execute code in.
The container itself (image, GPU, limits, mounts, hardening) is defined by the
`sandbox` service in docker-compose.yml; this only says which service to run
and how commands are run in it. One container is started per search run
(shared by all portals) and removed at the end.
"""

from pathlib import Path

from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SandboxConfig(BaseModel):
    compose_file: Path = PROJECT_ROOT / "docker-compose.yml"
    # "sandbox" (CUDA) or "sandbox-cpu" (no NVIDIA toolkit needed).
    service: str = "sandbox"
    name_prefix: str = "careerai-sbx"
    # Must match the label set on the service in docker-compose.yml.
    label: str = "careerai.sandbox=1"

    # Execution behaviour (per `docker exec` call)
    exec_timeout_s: int = 60
    max_output_chars: int = 4000
