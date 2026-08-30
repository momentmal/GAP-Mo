import pytest

from geo_activity_playground.core import host_resources
from geo_activity_playground.core.host_resources import (
    MEMORY_PER_WORKER,
    available_memory,
    default_worker_count,
)


@pytest.fixture
def cgroup_files(tmp_path, monkeypatch):
    v2 = tmp_path / "memory.max"
    v1 = tmp_path / "limit_in_bytes"
    monkeypatch.setattr(host_resources, "_CGROUP_V2_LIMIT", v2)
    monkeypatch.setattr(host_resources, "_CGROUP_V1_LIMIT", v1)
    return v2, v1


def test_cgroup_v2_limit_is_used(cgroup_files) -> None:
    v2, _ = cgroup_files
    v2.write_text("2147483648\n")
    assert available_memory() == 2147483648


def test_cgroup_v1_limit_is_used_when_v2_is_absent(cgroup_files) -> None:
    _, v1 = cgroup_files
    v1.write_text("1073741824\n")
    assert available_memory() == 1073741824


def test_unlimited_cgroup_falls_back_to_physical_memory(cgroup_files) -> None:
    v2, _ = cgroup_files
    v2.write_text("max\n")
    assert available_memory() > 0


def test_cgroup_v1_sentinel_falls_back_to_physical_memory(cgroup_files) -> None:
    _, v1 = cgroup_files
    v1.write_text(f"{2**63 - 1}\n")
    assert available_memory() < 2**62


def test_missing_cgroup_falls_back_to_physical_memory(cgroup_files) -> None:
    assert available_memory() > 0


def test_worker_count_is_limited_by_memory(cgroup_files, monkeypatch) -> None:
    v2, _ = cgroup_files
    v2.write_text(str(2 * MEMORY_PER_WORKER))
    monkeypatch.setattr(host_resources.os, "cpu_count", lambda: 64)
    assert default_worker_count() == 2


def test_worker_count_is_limited_by_cpus(cgroup_files, monkeypatch) -> None:
    v2, _ = cgroup_files
    v2.write_text(str(64 * MEMORY_PER_WORKER))
    monkeypatch.setattr(host_resources.os, "cpu_count", lambda: 2)
    assert default_worker_count() == 2


def test_worker_count_is_capped(cgroup_files, monkeypatch) -> None:
    v2, _ = cgroup_files
    v2.write_text(str(64 * MEMORY_PER_WORKER))
    monkeypatch.setattr(host_resources.os, "cpu_count", lambda: 64)
    assert default_worker_count() == host_resources.MAX_DEFAULT_WORKERS


def test_worker_count_is_at_least_one(cgroup_files, monkeypatch) -> None:
    v2, _ = cgroup_files
    v2.write_text(str(MEMORY_PER_WORKER // 4))
    monkeypatch.setattr(host_resources.os, "cpu_count", lambda: 1)
    assert default_worker_count() == 1
