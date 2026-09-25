"""
A bash shell inside a throwaway container started from the `sandbox` service in
docker-compose.yml. The container just idles (`sleep infinity`); every call is a
fresh `docker exec`, so nothing stays in memory between calls, but files under
/workspace (a tmpfs) persist for the life of the session:

    with SandboxSession(SandboxConfig()) as sbx:
        sbx.run("echo hi > note.txt")
        sbx.run("cat note.txt")                      # bash
        sbx.run_python("print(open('note.txt').read())")  # python3 -

The container is removed when the session closes.
"""

import subprocess
import uuid

from agents.sandbox.config import SandboxConfig

WORKDIR = "/workspace"


class SandboxError(RuntimeError):
    pass


class SandboxSession:
    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self.name: str | None = None

    # ── lifecycle ─────────────────────────────────────────

    def start(self) -> "SandboxSession":
        self.name = f"{self.config.name_prefix}-{uuid.uuid4().hex[:8]}"
        try:
            _docker(
                "compose", "-f", str(self.config.compose_file),
                "run", "-d", "--rm", "--name", self.name,
                self.config.service,
            )
        except Exception as e:
            self.close()
            raise SandboxError(f"Sandbox failed to start: {e}") from e
        return self

    def close(self) -> None:
        if self.name is not None:
            _docker("rm", "-f", self.name, check=False)
            self.name = None

    def __enter__(self) -> "SandboxSession":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()

    # ── execution ─────────────────────────────────────────

    def run(self, script: str, timeout: int | None = None, truncate: bool = True) -> dict:
        """Run a bash script in /workspace. Returns {"stdout", "stderr", "exit_code"}.

        Output is truncated to config.max_output_chars (it's meant for the LLM);
        pass truncate=False when reading data back for the program itself.
        """
        return self._exec(["bash", "-s"], script, timeout, truncate)

    def run_python(self, code: str, timeout: int | None = None, truncate: bool = True) -> dict:
        """Run Python source with `python3 -` in /workspace (same return shape as run)."""
        return self._exec(["python3", "-"], code, timeout, truncate)

    def read_file(self, path: str) -> str:
        """Full contents of a file in the sandbox (relative paths are under /workspace)."""
        out = self._exec(["cat", "--", path], "", None, truncate=False)
        if out["exit_code"] != 0:
            raise SandboxError(out["stderr"] or f"cannot read {path}")
        return out["stdout"]

    # ── helpers ───────────────────────────────────────────

    def _exec(self, cmd: list[str], stdin: str, timeout: int | None, truncate: bool) -> dict:
        if self.name is None:
            raise SandboxError("Sandbox is not running")
        timeout = timeout or self.config.exec_timeout_s
        cut = self._truncate if truncate else (lambda text: text)
        # `timeout` inside the container kills the process tree there; the
        # host-side timeout is only a backstop if docker itself hangs.
        proc_cmd = ["docker", "exec", "-i", "-w", WORKDIR, self.name, "timeout", "-k", "5", str(timeout), *cmd]
        try:
            proc = subprocess.run(proc_cmd, input=stdin, capture_output=True, text=True, timeout=timeout + 15)
        except subprocess.TimeoutExpired as e:
            return {"stdout": cut(_text(e.stdout)), "stderr": f"TimeoutError: exceeded {timeout}s", "exit_code": 124}
        stderr = proc.stderr
        if proc.returncode == 124:
            stderr += f"\nTimeoutError: exceeded {timeout}s and was killed"
        return {"stdout": cut(proc.stdout), "stderr": cut(stderr.strip()), "exit_code": proc.returncode}

    def _truncate(self, text: str) -> str:
        limit = self.config.max_output_chars
        if len(text) <= limit:
            return text
        half = limit // 2
        return f"{text[:half]}\n...[{len(text) - limit} chars truncated]...\n{text[-half:]}"


def cleanup_orphans(config: SandboxConfig | None = None) -> int:
    """Remove sandbox containers left behind by crashed runs."""
    config = config or SandboxConfig()
    ids = _docker("ps", "-aq", "--filter", f"label={config.label}").split()
    if ids:
        _docker("rm", "-f", *ids, check=False)
    return len(ids)


def _docker(*args: str, check: bool = True) -> str:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True)
    if not check:
        return (proc.stdout + proc.stderr).strip()  # e.g. `docker logs` writes to both
    if proc.returncode != 0:
        raise SandboxError(proc.stderr.strip() or proc.stdout.strip())
    return proc.stdout.strip()


def _text(data: bytes | str | None) -> str:
    if isinstance(data, bytes):
        return data.decode(errors="replace")
    return data or ""
