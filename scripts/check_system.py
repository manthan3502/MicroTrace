"""Local Compose reliability/privacy E2E. Keeps existing data and the named volume."""

import argparse
import json
import secrets
import subprocess
import time
from pathlib import Path

import httpx


def run(docker, order_url, backend_url):
    root = Path(__file__).resolve().parents[1]

    def compose(*args):
        result = subprocess.run(
            [docker, "compose", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        # Do not echo container configuration or logs if a command fails.
        assert result.returncode == 0, (
            f"Compose {args[0]} failed (exit {result.returncode})"
        )
        return result.stdout

    def restore(service):
        compose("up", "-d", "--wait", "--wait-timeout", "120", service)

    with httpx.Client(timeout=10) as client:
        canaries = ["qa-" + secrets.token_hex(16) for _ in range(3)]
        response = client.post(
            order_url + "/orders",
            json={"item": canaries[0], "scenario": "normal"},
            headers={
                "Authorization": "Bearer " + canaries[1],
                "Cookie": "qa=" + canaries[2],
            },
        )
        assert response.status_code == 200
        trace_id = response.json()["trace_id"]
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = client.get(backend_url + "/api/v1/traces/" + trace_id)
            if result.status_code == 200 and result.json()["trace"]["span_count"] == 8:
                break
            time.sleep(0.02)
        assert result.status_code == 200 and result.json()["trace"]["span_count"] == 8
        original = result.json()
        assert not any(token in result.text for token in canaries), (
            "Sensitive telemetry captured"
        )
        assert all(
            set(span["attributes"])
            <= {
                "http.method",
                "http.route",
                "http.status_code",
                "peer.service",
                "order.id",
                "demo.scenario",
            }
            for span in original["spans"]
        )
        print(
            "PASS: real stored spans contain no auth, cookie or request-body canaries"
        )

        try:
            compose("stop", "trace-backend")
            for _ in range(3):
                assert client.post(order_url + "/orders", json={}).status_code == 200
            time.sleep(
                2
            )  # Let failed deliveries expire before restarting the collector.
            print(
                "PASS: three normal business requests succeed while collector is stopped"
            )
        finally:
            restore("trace-backend")
        assert client.get(backend_url + "/api/v1/traces/" + trace_id).json() == original
        print("PASS: collector restart preserves the exact stored trace")

        container = compose("ps", "-q", "postgres").strip()

        def volume_identity():
            result = subprocess.run(
                [docker, "inspect", "--format", "{{json .Mounts}}", container],
                capture_output=True,
                text=True,
                check=True,
            )
            mounts = json.loads(result.stdout)
            return next(
                m["Name"]
                for m in mounts
                if m["Destination"] == "/var/lib/postgresql/data"
            )

        before = volume_identity()
        try:
            compose("stop", "postgres")
            for path in ("/health", "/api/v1/traces", "/api/v1/services"):
                result = client.get(backend_url + path)
                assert result.status_code == 503
                assert result.json() == {"detail": "Database unavailable"}
            assert client.post(order_url + "/orders", json={}).status_code == 200
            print(
                "PASS: database outage is sanitized and does not fail normal business traffic"
            )
        finally:
            restore("postgres")
        assert volume_identity() == before
        assert client.get(backend_url + "/api/v1/traces/" + trace_id).json() == original
        assert client.get(backend_url + "/health").status_code == 200
        print("PASS: PostgreSQL restart preserves volume and exact stored trace")
        logs = compose("logs", "--no-color", "--no-log-prefix")
        assert not any(token in logs for token in canaries), (
            "Sensitive value appeared in logs"
        )
        print("PASS: service/container logs contain no sensitive request canaries")
        stored = compose(
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At '
            "-c 'SELECT row_to_json(s)::text FROM spans s'",
        )
        configuration = subprocess.run(
            [docker, "inspect", "--format", "{{json .Config.Env}}", container],
            capture_output=True,
            text=True,
            check=True,
        )
        # Read the local secret only in memory; never print it or container configuration.
        password = next(
            value.split("=", 1)[1]
            for value in json.loads(configuration.stdout)
            if value.startswith("POSTGRES_PASSWORD=")
        )
        assert password and password not in stored and password not in logs, (
            "Database secret appeared in persisted spans or logs"
        )
        assert not any(token in stored for token in canaries), (
            "Sensitive value persisted"
        )
        print(
            "PASS: all persisted spans and logs exclude the database secret and request canaries"
        )
    print(f"System reliability/privacy E2E: PASS trace_id={trace_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--docker", default="docker", help="Docker executable or absolute CLI path"
    )
    parser.add_argument("--order-url", default="http://localhost:8001")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    args = parser.parse_args()
    run(args.docker, args.order_url.rstrip("/"), args.backend_url.rstrip("/"))
