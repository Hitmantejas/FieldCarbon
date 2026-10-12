"""The figure contract refuses unlabelled, unsourced or malformed figures."""
import pytest

from backend.tools.contracts import Figure, weakest


def test_a_valid_figure_and_a_range_only_figure():
    assert Figure(10.0, "L", "measured", "x", source_ids=("tum_alc_data",)).value == 10.0
    cost = Figure(None, "GBP", "estimated", "x", source_ids=("defra_ukammg",), low=1.0, high=2.0)
    assert (cost.low, cost.high) == (1.0, 2.0)


@pytest.mark.parametrize("kwargs, message", [
    (dict(label="verified"), "label"),
    (dict(source_ids=()), "source_id"),
    (dict(value=None), "range"),
    (dict(low=5.0, high=1.0), "above"),
])
def test_invalid_figures_are_rejected(kwargs, message):
    base = dict(value=1.0, unit="L", label="measured", how="x", source_ids=("tum_alc_data",))
    with pytest.raises(ValueError, match=message):
        Figure(**{**base, **kwargs})


def test_weakest_label_wins():
    assert weakest(["measured", "allocated"]) == "allocated"
    assert weakest(["measured", "estimated", "allocated"]) == "estimated"
    assert weakest(["measured"]) == "measured"
