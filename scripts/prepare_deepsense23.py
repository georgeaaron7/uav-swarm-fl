"""Prepare DeepSense 6G Scenario 23 for the FL channel simulator.

The raw archive is not redistributed. Download Scenario 23 from the official
DeepSense site, extract it, and point this script at the directory containing
``scenario23.csv``.
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
from pathlib import Path

import numpy as np


def clean_path(value: str) -> str:
    value = value.strip()
    try:
        parsed = ast.literal_eval(value)
        if isinstance(parsed, (list, tuple)) and len(parsed) == 1:
            value = str(parsed[0])
    except (ValueError, SyntaxError):
        pass
    return value.strip("[]'\" ").replace("\\", "/")


def load_numbers(root: Path, relative: str) -> np.ndarray:
    path = root / clean_path(relative)
    values = np.loadtxt(path, dtype=float)
    return np.asarray(values).reshape(-1)


def scalar(root: Path, row: dict, key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    if not value:
        return default
    numbers = load_numbers(root, value)
    return float(numbers[0]) if len(numbers) else default


def timestamp_ms(value: str) -> float:
    text = value.strip("[]'\" ")
    parts = text.split("-")
    if len(parts) != 4:
        return float("nan")
    hour, minute, second, millis = map(float, parts)
    return ((hour * 60 + minute) * 60 + second) * 1000 + millis


def gps_to_local(gps: np.ndarray, origin: np.ndarray) -> tuple[float, float]:
    lat, lon = gps[:2]
    lat0, lon0 = origin[:2]
    earth_radius_m = 6_371_000.0
    x = math.radians(lon - lon0) * earth_radius_m * math.cos(math.radians((lat + lat0) / 2))
    y = math.radians(lat - lat0) * earth_radius_m
    return x, y


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario_dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("data/channel_traces/deepsense23.npz"))
    parser.add_argument(
        "--power-domain", choices=("db", "linear"), default="linear",
        help="interpret the recorded beam-power vector as dB values or linear power",
    )
    args = parser.parse_args()
    root = args.scenario_dir.resolve()
    csv_path = root / "scenario23.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"expected {csv_path}")

    columns = {
        "power": "unit1_pwr_60ghz",
        "bs_gps": "unit1_loc",
        "uav_gps": "unit2_loc",
        "distance": "unit2_distance",
        "height": "unit2_height",
        "speed": "unit2_speed",
        "pitch": "unit2_pitch",
        "roll": "unit2_roll",
        "sequence": "seq_index",
        "timestamp": "time_stamp[UTC]",
        "beam_index": "unit1_beam_index",
    }
    output = {name: [] for name in (
        "rx_power_db", "x_m", "y_m", "distance_m", "height_m", "speed",
        "pitch_deg", "roll_deg", "sequence_id", "timestamp_ms",
    )}
    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [value for value in columns.values() if value not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"scenario23.csv is missing columns: {', '.join(missing)}")
        origin = None
        beam_mismatches = 0
        for row in reader:
            bs_gps = load_numbers(root, row[columns["bs_gps"]])
            origin = bs_gps if origin is None else origin
            uav_gps = load_numbers(root, row[columns["uav_gps"]])
            x_m, y_m = gps_to_local(uav_gps, origin)
            beam_power = load_numbers(root, row[columns["power"]])
            if len(beam_power) != 64:
                raise ValueError(f"expected 64 beam powers at source row {row['index']}")
            recorded_beam = int(float(clean_path(row[columns["beam_index"]])))
            beam_mismatches += int(int(np.argmax(beam_power)) + 1 != recorded_beam)
            best_power = float(np.max(beam_power))
            if args.power_domain == "linear":
                best_power = 10.0 * math.log10(max(best_power, 1e-30))
            output["rx_power_db"].append(best_power)
            output["x_m"].append(x_m)
            output["y_m"].append(y_m)
            output["distance_m"].append(0.3048 * scalar(root, row, columns["distance"]))
            output["height_m"].append(0.3048 * scalar(root, row, columns["height"]))
            output["speed"].append(scalar(root, row, columns["speed"]))
            output["pitch_deg"].append(scalar(root, row, columns["pitch"]))
            output["roll_deg"].append(scalar(root, row, columns["roll"]))
            output["sequence_id"].append(int(float(clean_path(row[columns["sequence"]]))))
            output["timestamp_ms"].append(timestamp_ms(row[columns["timestamp"]]))

    arrays = {key: np.asarray(value) for key, value in output.items()}
    numeric_fields = [name for name in arrays if name != "sequence_id"]
    invalid = {name: int((~np.isfinite(arrays[name])).sum()) for name in numeric_fields}
    invalid = {name: count for name, count in invalid.items() if count}
    if invalid:
        raise ValueError(f"non-finite prepared values: {invalid}")
    if (arrays["distance_m"] <= 0).any() or (arrays["height_m"] < 0).any():
        raise ValueError("distance must be positive and height must be non-negative")
    metadata = {
        "source": "DeepSense 6G Scenario 23",
        "source_url": "https://www.deepsense6g.net/scenarios/Scenarios%2020-29/scenario-23",
        "source_paper_url": "https://doi.org/10.1109/OJCOMS.2025.3612320",
        "raw_rows": len(output["rx_power_db"]),
        "power_transform": f"max(64-beam vector), domain={args.power_domain}, converted to relative dB",
        "power_units": "dB relative to the dataset's arbitrary measurement scale; not dBm",
        "power_reference_db": float(np.median(output["rx_power_db"])),
        "distance_height_transform": "source feet multiplied by 0.3048 to metres",
        "speed_units": "source units not asserted; values retained unchanged",
        "beam_index_mismatches": beam_mismatches,
        "sequence_count": int(len(np.unique(arrays["sequence_id"]))),
        "note": "Multi-BS links are simulated from this measured single-BS reference trace.",
    }
    if beam_mismatches:
        raise ValueError(f"{beam_mismatches} recorded beam indices disagree with the power vectors")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, **arrays, metadata_json=np.array(json.dumps(metadata)))
    print(f"wrote {len(output['rx_power_db'])} samples to {args.out}")


if __name__ == "__main__":
    main()
