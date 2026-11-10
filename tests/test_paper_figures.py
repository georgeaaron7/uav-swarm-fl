import numpy as np
import pytest

from scripts.make_paper_figures import format_number, per_curves


def test_publication_rounding_does_not_print_negative_zero():
    assert format_number(-0.0001, digits=2) == "0.00"
    assert format_number(-0.04, signed=True) == "+0.0"
    assert format_number(-0.06, signed=True) == "-0.1"


def test_normal_approximation_at_capacity_uses_half_log_correction():
    curves = per_curves()
    at_capacity = np.flatnonzero(np.isclose(curves["snr"], 3.0)).item()
    # Independent reference for a 32,768-bit packet at the 3 dB capacity rate.
    # The erroneous full-log term gives about 0.4708, rather than 0.4854.
    assert curves["sharp"][at_capacity] == pytest.approx(0.48538765791091526)
    assert np.all(np.diff(curves["sharp"]) <= 0)
    assert curves["max_gap"] < 0.011
