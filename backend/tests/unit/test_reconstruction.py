import random
from datetime import timedelta

import pytest

from services.trace_backend.reconstruction import reconstruct
from tests.trace_fixtures import START, TRACE_ID, healthy, row


def test_canonical_tree_and_summary_contract():
    detail = reconstruct(healthy())
    assert [s["span_id"] for s in detail["spans"]] == [f"{i:016x}" for i in range(1, 9)]
    assert [s["depth"] for s in detail["spans"]] == [0, 1, 1, 2, 3, 1, 2, 3]
    assert detail["orphan_span_ids"] == []
    assert detail["trace"] == {
        "trace_id": TRACE_ID,
        "root_operation": "POST /orders",
        "start_time": START,
        "duration_us": 10000,
        "status": "OK",
        "span_count": 8,
        "incomplete": False,
        "services": ["notification-service", "order-service", "payment-service"],
    }
    assert [s["start_offset_us"] for s in detail["spans"]] == [
        0,
        1000,
        2000,
        3000,
        4000,
        7000,
        8000,
        8000,
    ]


@pytest.mark.parametrize("seed", range(10))
def test_random_arrival_order_has_identical_reconstruction(seed):
    rows = healthy()
    random.Random(seed).shuffle(rows)
    assert reconstruct(rows) == reconstruct(healthy())


def test_siblings_tie_break_by_span_id():
    rows = [row(1), row(3, 1), row(2, 1)]
    assert [s["span_id"] for s in reconstruct(rows)["spans"]] == [f"{i:016x}" for i in (1, 2, 3)]


def test_orphan_subtree_preserves_depth_and_only_orphan_root_is_marked():
    rows = [s for s in healthy() if s["span_id"] != f"{3:016x}"]
    result = reconstruct(rows)
    assert result["trace"]["incomplete"] and result["trace"]["status"] == "OK"
    assert result["orphan_span_ids"] == [f"{4:016x}"]
    assert [s["span_id"] for s in result["spans"]][-2:] == [f"{4:016x}", f"{5:016x}"]
    assert [s["depth"] for s in result["spans"]][-2:] == [0, 1]
    assert [s["is_orphan"] for s in result["spans"]][-2:] == [True, False]


def test_root_missing_uses_wall_window_and_incomplete_label():
    result = reconstruct(healthy()[1:])
    assert result["trace"]["root_operation"] == "incomplete trace"
    assert result["trace"]["duration_us"] == 8000
    assert result["trace"]["start_time"] == START + timedelta(milliseconds=1)
    assert result["trace"]["incomplete"]


def test_multiple_roots_choose_earliest_but_use_window_duration():
    result = reconstruct(
        [row(2, start_ms=10, duration_us=2000, operation="later"), row(1, operation="first")]
    )
    assert result["trace"]["root_operation"] == "first"
    assert result["trace"]["duration_us"] == 12000
    assert result["trace"]["incomplete"]


@pytest.mark.parametrize("failed", [0, 4, 7])
def test_any_error_sets_summary_error(failed):
    rows = healthy()
    rows[failed]["status"] = "ERROR"
    assert reconstruct(rows)["trace"]["status"] == "ERROR"


@pytest.mark.parametrize(
    "rows", [[row(1, 1)], [row(1, 2), row(2, 1)], [row(1), row(2, 3), row(3, 2)]]
)
def test_cycle_returns_every_span_once_and_marks_incomplete(rows):
    result = reconstruct(rows)
    assert result["trace"]["incomplete"]
    assert len(result["spans"]) == len(rows)
    assert len({s["span_id"] for s in result["spans"]}) == len(rows)
    assert result == reconstruct(list(reversed(rows)))


def test_deep_chain_avoids_python_recursion_limit():
    rows = [row(i, i - 1 if i > 1 else None) for i in range(1, 2001)]
    result = reconstruct(rows)
    assert len(result["spans"]) == 2000
    assert result["spans"][-1]["depth"] == 1999
    assert not result["trace"]["incomplete"]


def test_monotonic_root_duration_and_skewed_offsets_remain_separate():
    root, child = row(1, duration_us=0), row(2, 1, start_ms=-1)
    result = reconstruct([root, child])
    assert result["trace"]["duration_us"] == 0
    assert result["trace"]["start_time"] == child["start_time"]
    assert [s["start_offset_us"] for s in result["spans"]] == [1000, 0]
    assert all(s["start_offset_us"] >= 0 for s in result["spans"])


def test_empty_trace_rejected():
    with pytest.raises(ValueError):
        reconstruct([])
