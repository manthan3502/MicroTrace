"""Compose E2E: three real scenarios through export, PostgreSQL and query APIs."""

import argparse
import time

import httpx


def run(order_url, backend_url, slow_ms=300):
    results = {}
    with httpx.Client(timeout=10) as client:
        for mode, scenario in [
            ("healthy", "normal"),
            ("slow", "slow_payment"),
            ("error", "payment_error"),
        ]:
            response = client.post(
                order_url + "/orders", json={"scenario": scenario, "slow_ms": slow_ms}
            )
            assert response.status_code == (502 if mode == "error" else 200)
            trace_id = response.json()["trace_id"]
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                answer = client.get(backend_url + "/api/v1/traces/" + trace_id)
                data = answer.json()
                if answer.status_code == 200 and data["trace"]["span_count"] == (
                    5 if mode == "error" else 8
                ):
                    break
                time.sleep(0.02)
            entries = data["spans"]
            by_op = {(s["service_name"], s["operation_name"]): s for s in entries}
            root = by_op["order-service", "POST /orders"]
            caller = by_op["order-service", "POST payment-service /charge"]
            server = by_op["payment-service", "POST /charge"]
            internal = by_op["payment-service", "process-payment"]
            assert root["parent_span_id"] is None and not data["trace"]["incomplete"]
            assert {s["trace_id"] for s in entries} == {trace_id}
            assert len({s["span_id"] for s in entries}) == len(entries)
            assert caller["parent_span_id"] == root["span_id"]
            assert server["parent_span_id"] == caller["span_id"]
            assert internal["parent_span_id"] == server["span_id"]
            assert [s["span_kind"] for s in (root, caller, server, internal)] == [
                "SERVER",
                "CLIENT",
                "SERVER",
                "INTERNAL",
            ]
            if mode == "error":
                assert data["trace"]["status"] == "ERROR"
                assert all(
                    s["status"] == "ERROR" for s in (root, caller, server, internal)
                )
                assert not any(
                    s["service_name"] == "notification-service" for s in entries
                )
                assert by_op["order-service", "validate-order"]["status"] == "OK"
            else:
                assert all(s["status"] == "OK" for s in entries)
                downstream = by_op["notification-service", "POST /notify"]
                upstream = by_op["order-service", "POST notification-service /notify"]
                assert downstream["parent_span_id"] == upstream["span_id"]
                if mode == "slow":
                    assert internal["duration_us"] >= (slow_ms - 5) * 1000
                    assert (
                        root["duration_us"]
                        >= caller["duration_us"]
                        >= server["duration_us"]
                        >= internal["duration_us"]
                    )
            assert all("slow" not in s and "anomaly" not in s for s in entries)
            results[mode] = trace_id
            print(f"{mode}: PASS trace_id={trace_id} spans={len(entries)}")
    print("Scenario E2E: PASS")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-url", default="http://localhost:8001")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    args = parser.parse_args()
    run(args.order_url.rstrip("/"), args.backend_url.rstrip("/"))
