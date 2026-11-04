"""Admission control is deliberately separate from scientific configuration."""

import os

MODES = {"light": 1, "balanced": 2, "dedicated": max(1, min(8, os.cpu_count() or 2))}


def preferences(config):
    mode = config.get("mode", "balanced")
    if mode not in MODES:
        raise ValueError("mode must be light, balanced or dedicated")
    if int(config.get("cpu_threads", MODES[mode])) < 1:
        raise ValueError("CPU threads must be positive")
    if not 0 <= int(config.get("min_battery", 20)) <= 100:
        raise ValueError("minimum battery must be 0–100")
    return {
        "mode": mode,
        "cpu_threads": int(config.get("cpu_threads", MODES[mode])),
        "max_concurrent": 1,
        "allow_battery": bool(config.get("allow_battery", False)),
        "min_battery": int(config.get("min_battery", 20)),
        "max_temperature": int(config.get("max_temperature", 85)),
        "vram_budget_mb": int(config.get("vram_budget_mb", 0)),
        "allow_cpu": bool(config.get("allow_cpu", False)),
        "storage_limit_bytes": int(config.get("storage_limit_bytes", 20 * 1024**3)),
        "admin_permissions": config.get("admin_permissions", []),
    }


def admit(config, metrics):
    prefs = preferences(config)
    if metrics.get("on_battery") and not prefs["allow_battery"]:
        return False, "battery training disabled"
    if (
        metrics.get("battery_percent") is not None
        and metrics["battery_percent"] < prefs["min_battery"]
    ):
        return False, "battery below minimum"
    if (
        metrics.get("gpu_temperature") is not None
        and metrics["gpu_temperature"] >= prefs["max_temperature"]
    ):
        return False, "GPU above temperature limit"
    if prefs["mode"] == "light" and metrics.get("cpu_percent", 0) > 20:
        return False, "waiting for lower CPU activity"
    if metrics.get("disk_free_bytes", 0) < 1024**3:
        return False, "less than 1 GiB free disk"
    return True, None


def environment(config):
    threads = str(preferences(config)["cpu_threads"])
    return {
        **os.environ,
        "OMP_NUM_THREADS": threads,
        "MKL_NUM_THREADS": threads,
        "OPENBLAS_NUM_THREADS": threads,
        "PYTHONUNBUFFERED": "1",
    }
