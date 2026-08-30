import os
import pathlib

MEMORY_PER_WORKER = 400 * 1024**2
MAX_DEFAULT_WORKERS = 4

_CGROUP_V2_LIMIT = pathlib.Path("/sys/fs/cgroup/memory.max")
_CGROUP_V1_LIMIT = pathlib.Path("/sys/fs/cgroup/memory/limit_in_bytes")


def available_memory() -> int | None:
    """Memory available to this process, honoring container limits."""
    for path in (_CGROUP_V2_LIMIT, _CGROUP_V1_LIMIT):
        try:
            content = path.read_text().strip()
        except OSError:
            continue
        if content == "max":
            break
        try:
            limit = int(content)
        except ValueError:
            continue
        # Cgroup v1 reports an absurdly large number instead of "max".
        if limit < 2**62:
            return limit
        break

    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return None


def default_worker_count() -> int:
    """Worker processes that fit into the available CPU cores and memory."""
    candidates = [MAX_DEFAULT_WORKERS]
    if cpus := os.cpu_count():
        candidates.append(cpus)
    if memory := available_memory():
        candidates.append(memory // MEMORY_PER_WORKER)
    return max(1, min(candidates))
