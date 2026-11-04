"""Unavailable sensors are null, never guessed."""

from __future__ import annotations

import platform
import shutil
from pathlib import Path

import psutil

from ..shared.hashing import sha256


def telemetry(root=None):
    battery = psutil.sensors_battery()
    result = {
        "cpu_percent": psutil.cpu_percent(),
        "ram_percent": psutil.virtual_memory().percent,
        "ram_available_mb": psutil.virtual_memory().available // 1024**2,
        "disk_free_bytes": shutil.disk_usage(root or Path.home()).free,
        "on_battery": not battery.power_plugged if battery else None,
        "battery_percent": battery.percent if battery else None,
        "gpu_utilization": None,
        "gpu_memory_used_mb": None,
        "gpu_temperature": None,
        "gpu_power_w": None,
    }
    try:
        import pynvml as n

        n.nvmlInit()
        try:
            h = n.nvmlDeviceGetHandleByIndex(0)
            for key, fn in {
                "gpu_utilization": lambda: n.nvmlDeviceGetUtilizationRates(h).gpu,
                "gpu_memory_used_mb": lambda: (
                    n.nvmlDeviceGetMemoryInfo(h).used // 1024**2
                ),
                "gpu_temperature": lambda: n.nvmlDeviceGetTemperature(
                    h, n.NVML_TEMPERATURE_GPU
                ),
                "gpu_power_w": lambda: n.nvmlDeviceGetPowerUsage(h) / 1000,
            }.items():
                try:
                    result[key] = fn()
                except n.NVMLError:
                    pass
        finally:
            n.nvmlShutdown()
    except (ImportError, Exception):
        pass
    return result


def capabilities(config, test_cuda=True):
    from run_context_study import source_digest

    result = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "source_sha256": source_digest(),
        "cpu_count": psutil.cpu_count(logical=False),
        "ram_mb": psutil.virtual_memory().total // 1024**2,
        "cuda": False,
        "gpu_count": 0,
        "gpu_name": None,
        "gpu_uuid": None,
        "vram_mb": 0,
        "datasets": {},
        "ready": False,
        "diagnostics": [],
    }
    try:
        import torch

        result.update(torch=str(torch.__version__), cuda_version=torch.version.cuda)
        if torch.cuda.is_available():
            if test_cuda:
                value = torch.ones(16, device="cuda")
                result["cuda_test"] = bool((value + 1).sum().item() == 32)
            result.update(
                cuda=True,
                gpu_count=torch.cuda.device_count(),
                gpu_name=torch.cuda.get_device_name(0),
                vram_mb=torch.cuda.get_device_properties(0).total_memory // 1024**2,
            )
        elif config.get("allow_cpu"):
            result["diagnostics"].append(
                "CPU pilot mode; not NVIDIA production validation"
            )
        else:
            result["diagnostics"].append(
                "CUDA is unavailable; install a compatible PyTorch wheel and NVIDIA driver"
            )
    except (ImportError, RuntimeError, OSError) as exc:
        result["diagnostics"].append(str(exc))
    for key, path in [
        ("dataset_sha256", Path(config.get("data_dir", "data")) / "cifar10.npz"),
        (
            "trace_sha256",
            Path(config.get("trace_path", "data/channel_traces/deepsense23.npz")),
        ),
    ]:
        if path.is_file():
            result["datasets"][key] = sha256(path)
        elif key == "dataset_sha256":
            result["diagnostics"].append(f"prepared dataset missing: {path}")
        else:
            result["datasets"][key] = None
    pilot = Path(config.get("data_dir", "data")) / "context_pilot/cifar10.npz"
    result["dataset_variants"] = list(
        filter(
            None,
            [
                result["datasets"].get("dataset_sha256"),
                sha256(pilot) if pilot.is_file() else None,
            ],
        )
    )
    result["ready"] = bool(
        result.get("torch")
        and result["datasets"].get("dataset_sha256")
        and (result["cuda"] or config.get("allow_cpu"))
    )
    try:
        import pynvml as n

        n.nvmlInit()
        try:
            result["gpu_uuid"] = n.nvmlDeviceGetUUID(n.nvmlDeviceGetHandleByIndex(0))
            result["driver"] = n.nvmlSystemGetDriverVersion()
        finally:
            n.nvmlShutdown()
    except Exception:
        pass
    return result
