from eida_consistency.core import coverage as cov


def dt(s):
    return cov.parse_iso(s)


# --- parse_iso / tolerance ---
def test_parse_iso_naive_gets_utc():
    d = cov.parse_iso("2020-01-01T00:00:00")
    assert d.tzinfo is not None

def test_parse_iso_invalid_returns_none():
    assert cov.parse_iso("nope") is None
    assert cov.parse_iso("") is None

def test_tolerance_from_samplerate():
    assert cov.tolerance_seconds(100.0) == 0.5   # 1/100=0.01 -> floored to 0.5
    assert cov.tolerance_seconds(0.5) == 2.0     # 1/0.5=2.0 > floor
    assert cov.tolerance_seconds(None) == 0.5    # floor
    assert cov.tolerance_seconds("bad") == 0.5

# --- clip ---
def test_clip_drops_outside_and_trims():
    w0, w1 = dt("2020-01-01T00:10:00"), dt("2020-01-01T00:20:00")
    ivs = [(dt("2020-01-01T00:00:00"), dt("2020-01-01T00:15:00")),
           (dt("2020-01-01T00:30:00"), dt("2020-01-01T00:40:00"))]
    out = cov.clip_intervals(ivs, w0, w1)
    assert out == [(w0, dt("2020-01-01T00:15:00"))]

# --- merge ---
def test_merge_glues_within_tolerance():
    ivs = [(dt("2020-01-01T00:00:00"), dt("2020-01-01T00:01:00")),
           (dt("2020-01-01T00:01:00"), dt("2020-01-01T00:02:00"))]
    assert cov.merge_intervals(ivs, tol=1.0) == [(dt("2020-01-01T00:00:00"), dt("2020-01-01T00:02:00"))]

def test_merge_keeps_real_gap():
    ivs = [(dt("2020-01-01T00:00:00"), dt("2020-01-01T00:03:00")),
           (dt("2020-01-01T00:06:00"), dt("2020-01-01T00:09:00"))]
    assert len(cov.merge_intervals(ivs, tol=1.0)) == 2

# --- mismatch: the core scenarios ---
def test_identical_single_span_no_mismatch():       # scenario 1
    a = [(dt("2020-01-01T00:00:00"), dt("2020-01-01T00:10:00"))]
    assert cov.mismatch_intervals(a, list(a), tol=0.5) == []

def test_identical_midnight_split_no_mismatch():    # scenario 2 (#41)
    a = [(dt("2020-01-09T23:55:00"), dt("2020-01-09T23:59:59")),
         (dt("2020-01-10T00:00:00"), dt("2020-01-10T00:05:00"))]
    assert cov.mismatch_intervals(a, list(a), tol=0.01) == []

def test_big_shared_gap_no_mismatch():              # scenario 3
    a = [(dt("2020-01-01T00:00:00"), dt("2020-01-01T00:03:00")),
         (dt("2020-01-01T00:06:00"), dt("2020-01-01T00:09:00"))]
    assert cov.mismatch_intervals(a, list(a), tol=0.5) == []

def test_dataselect_hole_is_flagged():              # scenario 4
    a = [(dt("2020-01-01T00:00:00"), dt("2020-01-01T00:09:00"))]
    d = [(dt("2020-01-01T00:00:00"), dt("2020-01-01T00:03:00")),
         (dt("2020-01-01T00:06:00"), dt("2020-01-01T00:09:00"))]
    out = cov.mismatch_intervals(a, d, tol=0.5)
    assert out == [(dt("2020-01-01T00:03:00"), dt("2020-01-01T00:06:00"))]

def test_dataselect_extra_data_is_flagged():        # scenario 5
    a = [(dt("2020-01-01T00:00:00"), dt("2020-01-01T00:03:00"))]
    d = [(dt("2020-01-01T00:00:00"), dt("2020-01-01T00:06:00"))]
    out = cov.mismatch_intervals(a, d, tol=0.5)
    assert out == [(dt("2020-01-01T00:03:00"), dt("2020-01-01T00:06:00"))]

def test_both_empty_no_mismatch():                  # scenario 6
    assert cov.mismatch_intervals([], [], tol=0.5) == []

def test_one_side_empty_is_flagged():               # scenario 7/8
    a = [(dt("2020-01-01T00:00:00"), dt("2020-01-01T00:10:00"))]
    assert cov.mismatch_intervals(a, [], tol=0.5) == a
    assert cov.mismatch_intervals([], a, tol=0.5) == a

def test_subsample_edge_jitter_absorbed():          # scenario 9
    a = [(dt("2020-01-01T00:00:00.000"), dt("2020-01-01T00:10:00.000"))]
    d = [(dt("2020-01-01T00:00:00.003"), dt("2020-01-01T00:10:00.000"))]
    assert cov.mismatch_intervals(a, d, tol=0.5) == []

def test_mismatch_just_over_tolerance_is_flagged():  # scenario 10
    a = [(dt("2020-01-01T00:00:00"), dt("2020-01-01T00:10:00"))]
    d = [(dt("2020-01-01T00:00:02"), dt("2020-01-01T00:10:00"))]  # 2s > 0.5s
    assert cov.mismatch_intervals(a, d, tol=0.5) == [
        (dt("2020-01-01T00:00:00"), dt("2020-01-01T00:00:02"))
    ]
