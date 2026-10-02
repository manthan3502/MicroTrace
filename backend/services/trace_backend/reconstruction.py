from collections import defaultdict
from collections.abc import Mapping, Sequence

from microtrace_sdk.models import FinishedSpan


def microseconds(delta) -> int:
    return delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds


def reconstruct(rows: Sequence[Mapping]) -> dict:
    """ID-based deterministic traversal. Iterative walking also handles deep chains."""
    if not rows:
        raise ValueError("A trace requires at least one span")
    by_id = {row["span_id"]: row for row in rows}

    def key(row):
        return row["start_time"], row["span_id"]

    roots = sorted((row for row in rows if row["parent_span_id"] is None), key=key)
    orphans = sorted(
        (
            row
            for row in rows
            if row["parent_span_id"] is not None and row["parent_span_id"] not in by_id
        ),
        key=key,
    )
    children = defaultdict(list)
    for row in rows:
        if row["parent_span_id"] in by_id:
            children[row["parent_span_id"]].append(row)
    for group in children.values():
        group.sort(key=key)
    start = min(row["start_time"] for row in rows)
    visited = set()
    ordered = []
    orphan_ids = {row["span_id"] for row in orphans}

    def walk(first):
        pending = [(first, 0)]
        while pending:
            row, depth = pending.pop()
            identity = row["span_id"]
            if identity in visited:
                continue
            visited.add(identity)
            ordered.append(
                {
                    **{field: row[field] for field in FinishedSpan.model_fields},
                    "depth": depth,
                    "is_orphan": identity in orphan_ids,
                    "start_offset_us": max(0, microseconds(row["start_time"] - start)),
                }
            )
            pending.extend((child, depth + 1) for child in reversed(children[identity]))

    for row in roots + orphans:
        walk(row)
    # Remaining components contain cycles. Return each span once rather than repairing links.
    cyclic = len(visited) != len(by_id)
    for row in sorted(rows, key=key):
        if row["span_id"] not in visited:
            walk(row)
    delta = max(row["end_time"] for row in rows) - start
    summary = {
        "trace_id": rows[0]["trace_id"],
        "root_operation": roots[0]["operation_name"] if roots else "incomplete trace",
        "start_time": start,
        "duration_us": roots[0]["duration_us"] if len(roots) == 1 else max(0, microseconds(delta)),
        "status": "ERROR" if any(row["status"] == "ERROR" for row in rows) else "OK",
        "services": sorted({row["service_name"] for row in rows}),
        "span_count": len(rows),
        "incomplete": len(roots) != 1 or bool(orphans) or cyclic,
    }
    return {
        "trace": summary,
        "spans": ordered,
        "orphan_span_ids": [row["span_id"] for row in orphans],
    }
