import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np


def test_preprocessor_converts_linear_power_and_imperial_geometry(tmp_path):
    scenario = tmp_path / "scenario23"
    scenario.mkdir()
    files = {
        "power.txt": np.r_[np.ones(5), 4.0, np.ones(58)],
        "bs.txt": np.array([33.0, -111.0]),
        "uav.txt": np.array([33.00001, -110.99999]),
        "distance.txt": np.array([10.0]),
        "height.txt": np.array([20.0]),
        "speed.txt": np.array([3.0]),
        "pitch.txt": np.array([1.0]),
        "roll.txt": np.array([-2.0]),
    }
    for name, values in files.items():
        np.savetxt(scenario / name, values)

    columns = [
        "index", "unit1_pwr_60ghz", "unit1_loc", "unit2_loc", "unit2_distance",
        "unit2_height", "unit2_speed", "unit2_pitch", "unit2_roll", "seq_index",
        "time_stamp[UTC]", "unit1_beam_index",
    ]
    row = [
        "0", "power.txt", "bs.txt", "uav.txt", "distance.txt", "height.txt",
        "speed.txt", "pitch.txt", "roll.txt", "1", "12-00-00-100", "6",
    ]
    with (scenario / "scenario23.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerow(row)

    output = tmp_path / "prepared.npz"
    script = Path(__file__).parents[1] / "scripts" / "prepare_deepsense23.py"
    subprocess.run(
        [sys.executable, str(script), str(scenario), "--out", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    data = np.load(output, allow_pickle=False)
    np.testing.assert_allclose(data["rx_power_db"][0], 10 * np.log10(4.0))
    np.testing.assert_allclose(data["distance_m"][0], 3.048)
    np.testing.assert_allclose(data["height_m"][0], 6.096)
    metadata = json.loads(str(data["metadata_json"].item()))
    assert metadata["beam_index_mismatches"] == 0
    assert metadata["power_units"].endswith("not dBm")
