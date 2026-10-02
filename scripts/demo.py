"""Trigger one approved scenario; only Python's standard library is required."""

import argparse
import json
import urllib.error
import urllib.request


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["healthy", "slow", "error"])
    parser.add_argument("--order-url", default="http://localhost:8001")
    parser.add_argument("--dashboard-url", default="http://localhost:5173")
    parser.add_argument("--slow-ms", type=int, default=800)
    args = parser.parse_args(argv)
    if not 100 <= args.slow_ms <= 3000:
        parser.error("--slow-ms must be between 100 and 3000")
    scenario = {"healthy": "normal", "slow": "slow_payment", "error": "payment_error"}[
        args.mode
    ]
    request = urllib.request.Request(
        args.order_url.rstrip("/") + "/orders",
        data=json.dumps(
            {"item": "demo-item", "scenario": scenario, "slow_ms": args.slow_ms}
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            result = json.load(response)
            status = response.code
    except (urllib.error.URLError, TimeoutError, ValueError):
        print("Demo request failed; check Order Service availability")
        return 1
    print(f"HTTP {status}: {result.get('status', 'failed')}")
    trace_id = result.get("trace_id")
    if trace_id:
        print(f"Trace ID: {trace_id}")
        print(f"Trace URL: {args.dashboard_url.rstrip('/')}/traces/{trace_id}")
    expected = 502 if args.mode == "error" else 200
    return 0 if status == expected and trace_id else 1


if __name__ == "__main__":
    raise SystemExit(main())
