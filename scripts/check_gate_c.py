"""Run inside trace-backend via stdin against the deployed Compose services."""

import random
import time

import httpx
from microtrace_sdk.ids import new_span_id, new_trace_id
from services.trace_backend.database import get_engine
from services.trace_backend.db_models import spans
from sqlalchemy import delete, func, inspect, select

BACKEND = "http://trace-backend:8000"
ORDER = "http://order-service:8000"


def get_detail(client, trace_id, count):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"{BACKEND}/api/v1/traces/{trace_id}")
        if (
            response.status_code == 200
            and response.json()["trace"]["span_count"] == count
        ):
            return response.json()
        time.sleep(0.02)
    raise AssertionError("Persisted trace did not reach expected span count")


def payload(span):
    return {
        key: value
        for key, value in span.items()
        if key not in {"depth", "is_orphan", "start_offset_us"}
    }


def run():
    engine = get_engine()
    temporary = []
    with httpx.Client(timeout=5) as client:
        response = client.post(f"{ORDER}/orders", json={"scenario": "normal"})
        response.raise_for_status()
        trace_id = response.json()["trace_id"]
        detail = get_detail(client, trace_id, 8)
        by_op = {(s["service_name"], s["operation_name"]): s for s in detail["spans"]}
        root = by_op[("order-service", "POST /orders")]
        assert root["parent_span_id"] is None
        assert not detail["trace"]["incomplete"] and detail["trace"]["status"] == "OK"
        assert [s["depth"] for s in detail["spans"]] == [0, 1, 1, 2, 3, 1, 2, 3]
        assert len({s["span_id"] for s in detail["spans"]}) == 8
        for service, route, local in [
            ("payment-service", "/charge", "process-payment"),
            ("notification-service", "/notify", "send-notification"),
        ]:
            caller = by_op[("order-service", f"POST {service} {route}")]
            server = by_op[(service, f"POST {route}")]
            assert (
                caller["span_kind"] == "CLIENT"
                and caller["parent_span_id"] == root["span_id"]
            )
            assert (
                server["span_kind"] == "SERVER"
                and server["parent_span_id"] == caller["span_id"]
            )
            assert by_op[(service, local)]["parent_span_id"] == server["span_id"]
        assert (
            by_op[("order-service", "validate-order")]["parent_span_id"]
            == root["span_id"]
        )
        assert {s["trace_id"] for s in detail["spans"]} == {trace_id}
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    select(func.count())
                    .select_from(spans)
                    .where(spans.c.trace_id == trace_id)
                )
                == 8
            )
            assert set(inspect(connection).get_table_names()) == {
                "spans",
                "alembic_version",
            }
            assert inspect(connection).get_foreign_keys("spans") == []
        print(
            "PASS: real services -> bounded export -> collector -> PostgreSQL -> query -> exact eight-span tree"
        )
        for span in detail["spans"]:
            result = client.post(f"{BACKEND}/api/v1/spans", json=payload(span))
            assert result.status_code == 200 and result.json() == {
                "status": "duplicate"
            }
        assert get_detail(client, trace_id, 8) == detail
        items = client.get(
            f"{BACKEND}/api/v1/traces",
            params={
                "service": "payment-service",
                "status": "OK",
                "min_duration_ms": 0,
                "limit": 100,
            },
        ).json()["items"]
        assert any(item["trace_id"] == trace_id for item in items)
        print(
            "PASS: duplicate ingestion preserves originals; combined filters; only spans persistence model"
        )
        try:
            test_trace = new_trace_id()
            temporary.append(test_trace)
            parent_id, child_id = new_span_id(), new_span_id()
            parent = {
                **payload(root),
                "trace_id": test_trace,
                "span_id": parent_id,
                "operation_name": "gate-root",
            }
            child = {
                **parent,
                "span_id": child_id,
                "parent_span_id": parent_id,
                "operation_name": "gate-child",
                "span_kind": "INTERNAL",
            }
            assert client.post(f"{BACKEND}/api/v1/spans", json=child).status_code == 201
            missing = get_detail(client, test_trace, 1)
            assert missing["trace"]["incomplete"] and missing["orphan_span_ids"] == [
                child_id
            ]
            assert (
                client.post(f"{BACKEND}/api/v1/spans", json=parent).status_code == 201
            )
            completed = get_detail(client, test_trace, 2)
            assert (
                not completed["trace"]["incomplete"]
                and completed["orphan_span_ids"] == []
            )
            assert [s["depth"] for s in completed["spans"]] == [0, 1]
            for seed in range(3):
                shuffled_trace = new_trace_id()
                temporary.append(shuffled_trace)
                values = [payload(s) for s in detail["spans"]]
                random.Random(seed).shuffle(values)
                for value in values:
                    assert (
                        client.post(
                            f"{BACKEND}/api/v1/spans",
                            json={**value, "trace_id": shuffled_trace},
                        ).status_code
                        == 201
                    )
                actual = get_detail(client, shuffled_trace, 8)
                actual["trace"]["trace_id"] = trace_id
                for span in actual["spans"]:
                    span["trace_id"] = trace_id
                assert actual == detail
            cyclic_trace = new_trace_id()
            temporary.append(cyclic_trace)
            for identity, ancestor in [(parent_id, child_id), (child_id, parent_id)]:
                value = {
                    **parent,
                    "trace_id": cyclic_trace,
                    "span_id": identity,
                    "parent_span_id": ancestor,
                }
                assert (
                    client.post(f"{BACKEND}/api/v1/spans", json=value).status_code
                    == 201
                )
            cycle = get_detail(client, cyclic_trace, 2)
            assert cycle["trace"]["incomplete"] and len(cycle["spans"]) == 2
            print(
                "PASS: child-before-parent, missing parent/orphan, randomized arrival order and cycle safety"
            )
        finally:
            # Remove only synthetic telemetry created by this invocation. Keep the real order trace.
            with engine.begin() as connection:
                connection.execute(delete(spans).where(spans.c.trace_id.in_(temporary)))
    print("Gate C: PASS")


if __name__ == "__main__":
    run()
