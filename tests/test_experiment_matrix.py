from run_experiments import ATTACKS, scenario_matrix


def test_core_matrix_has_controlled_and_hierarchical_attack_cases():
    scenarios = scenario_matrix("trace.npz", "core")
    for attack in ATTACKS:
        assert f"{attack}_ideal" in scenarios
        assert f"{attack}_hfl_ideal" in scenarios
        assert f"{attack}_hfl_lossy" in scenarios
        assert f"{attack}_hfl_trace" in scenarios
    assert "clean_hfl_ideal" in scenarios
    trace_args = scenarios["clean_hfl_trace"]
    assert trace_args[trace_args.index("--trace-snr-reference-db") + 1] == "10"
    assert trace_args[trace_args.index("--trace-stride") + 1] == "5"
