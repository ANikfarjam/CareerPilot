"""
Frees memory after an agent run so the machine doesn't freeze.

chat_model keeps gpt-oss-20b (~13 GB) loaded with keep_alive=-1 so one run's many LLM
calls don't each reload it. On this machine (15 GB RAM, 8 GB VRAM) that leaves almost
nothing for anything else once the run is over, so every agent entry point calls
release_memory() when it finishes:

  1. unload_models()        asks the Ollama server to unload every loaded model
                            (keep_alive=0), which frees its weights and KV cache in RAM/VRAM.
                            The next run reloads it (~2 minutes).
  2. trim_process_memory()  garbage-collects this Python process (the graph state's
                            DataFrames, prompts, model replies) and hands the freed heap
                            back to the OS with glibc's malloc_trim.

Neither step raises: an unreachable Ollama server or a non-glibc libc is only logged.

Use:
    release_memory()            # after a run
    with released_memory(): ... # runs release_memory() on exit, even if the body raises
"""

import contextlib
import ctypes
import ctypes.util
import gc
import json
import logging
import urllib.error
import urllib.request

from agents.utils.langchainConfig import OLLAMA_URL

logger = logging.getLogger(__name__)


def _ollama(path: str, body: dict | None = None, base_url: str = OLLAMA_URL, timeout: float = 30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{base_url}{path}", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or b"{}")


def unload_models(base_url: str = OLLAMA_URL) -> list[str]:
    """Unloads every model the Ollama server has in memory (GET /api/ps, then keep_alive=0 per model).
    Returns the names unloaded; [] if none were loaded or the server isn't running."""
    try:
        loaded = [m["name"] for m in _ollama("/api/ps", base_url=base_url).get("models", [])]
    except (urllib.error.URLError, OSError, ValueError) as e:
        logger.debug("Ollama not reachable at %s, nothing to unload: %s", base_url, e)
        return []
    unloaded = []
    for name in loaded:
        try:
            _ollama("/api/generate", {"model": name, "keep_alive": 0}, base_url=base_url)
            unloaded.append(name)
        except (urllib.error.URLError, OSError, ValueError) as e:
            logger.warning("could not unload Ollama model %s: %s", name, e)
    return unloaded


def trim_process_memory() -> None:
    """Collects garbage and returns the freed heap to the OS (malloc_trim, glibc only)."""
    gc.collect()
    libc_name = ctypes.util.find_library("c")
    if libc_name is None:
        return
    try:
        ctypes.CDLL(libc_name).malloc_trim(0)
    except (OSError, AttributeError):  # not glibc (e.g. musl): gc.collect is all we can do
        pass


def release_memory() -> None:
    """Unloads the Ollama models and trims this process's memory. Call it when an agent run ends."""
    unloaded = unload_models()
    trim_process_memory()
    if unloaded:
        logger.info("released memory: unloaded %s from Ollama", ", ".join(unloaded))


@contextlib.contextmanager
def released_memory():
    """Runs the body, then release_memory(), even if the body raised."""
    try:
        yield
    finally:
        release_memory()
