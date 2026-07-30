import extract_float_all as efa


def test_summarize_counts_by_verdict():
    rows = [
        {"verdict": "confident", "value": 32.1},
        {"verdict": "confident", "value": 40.0},
        {"verdict": "ambiguous", "value": None},
    ]
    s = efa.summarize(rows)
    assert s["confident"] == 2
    assert s["ambiguous"] == 1
    assert s["total"] == 3
