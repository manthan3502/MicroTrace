"""Verify the production edge from outside Compose, plus local container boundaries."""

import argparse
import json
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from check_scenarios import run as scenarios

SERVICES = {
    "frontend",
    "order-service",
    "payment-service",
    "notification-service",
    "trace-backend",
    "postgres",
}


def run(
    url, docker, compose_file, http_only=False, check_restart=False, probe_ports=False
):
    root = Path(__file__).resolve().parents[1]

    def compose(*args):
        result = subprocess.run(
            [docker, "compose", "-f", compose_file, *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"Compose {args[0]} failed"
        return result.stdout

    def stack():
        configuration = json.loads(compose("config", "--format", "json"))
        assert set(configuration["services"]) == SERVICES
        for name, service in configuration["services"].items():
            assert service["restart"] == "unless-stopped"
            assert service.get("healthcheck")
            if name != "frontend":
                assert not service.get("ports"), (
                    f"Private service publishes a port: {name}"
                )
        ports = configuration["services"]["frontend"]["ports"]
        assert len(ports) == 1 and ports[0]["target"] == 80
        result = compose("ps", "--format", "json").strip()
        containers = (
            json.loads(result)
            if result.startswith("[")
            else [json.loads(line) for line in result.splitlines()]
        )
        assert {item["Service"] for item in containers} == SERVICES
        assert all(item["Health"] == "healthy" for item in containers)
        print(
            "PASS: six healthy containers; restart policies; only Nginx publishes a port"
        )

    def volume():
        container = compose("ps", "-q", "postgres").strip()
        mounts = json.loads(
            subprocess.check_output(
                [docker, "inspect", "--format", "{{json .Mounts}}", container],
                text=True,
            )
        )
        return next(
            m["Name"] for m in mounts if m["Destination"] == "/var/lib/postgresql/data"
        )

    if not http_only:
        stack()
    with httpx.Client(base_url=url, timeout=10) as client:
        page = client.get("/")
        assert page.status_code == 200 and 'id="root"' in page.text
        assert "@vite/client" not in page.text and "nginx" in page.headers.get(
            "server", ""
        )
        assert client.get("/traces").text == page.text
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/v1/traces").status_code == 200
        assert client.get("/api/v1/services").status_code == 200
        for path in ("/api/v1/traces", "/api/v1/services", "/health"):
            assert client.post(path).status_code == 405
        for path in ("/api/v1/spans", "/api/v1/spans/", "/api/v1/%73pans"):
            assert client.post(path, json={}).status_code == 404
            assert client.get(path).status_code == 404
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404
        assert client.get("/orders").status_code == 405
        invalid = client.get("/api/v1/traces", params={"service": "bad\x00name"})
        assert invalid.status_code == 422
        assert invalid.json() == {"detail": "Invalid service filter"}
        print(
            "PASS: static SPA and query allowlist; ingestion/docs blocked; methods restricted"
        )
        identities = scenarios(url, url)
        trace = identities["healthy"]
        original = client.get("/api/v1/traces/" + trace).json()
        assert client.get("/traces/" + trace).text == page.text
        span = {
            k: v
            for k, v in original["spans"][0].items()
            if k not in {"depth", "is_orphan", "start_offset_us"}
        }
        assert client.post("/api/v1/spans", json=span).status_code == 404
        assert client.post("/api/v1/traces/" + trace).status_code == 405
        print(
            "PASS: direct detail navigation; a valid span cannot use public ingestion"
        )
        if check_restart:
            before = volume()
            compose("restart", "postgres")
            compose("up", "-d", "--wait", "--wait-timeout", "120", "postgres")
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                result = client.get("/api/v1/traces/" + trace)
                if result.status_code == 200:
                    break
                time.sleep(0.2)
            assert result.status_code == 200 and result.json() == original
            assert volume() == before
            stack()
            print(
                "PASS: PostgreSQL restart preserves named volume and exact stored trace"
            )
    if probe_ports:
        host = urlsplit(url).hostname
        for port in (5432, 8000, 8001, 5173):
            try:
                connection = socket.create_connection((host, port), timeout=2)
            except OSError:
                continue
            connection.close()
            raise AssertionError(
                f"Unexpected reachable private/development port: {port}"
            )
        print("PASS: private/development TCP ports unreachable from this probe host")
    print(
        "Production smoke: PASS (this is Gate E evidence only on the actual deployed host)"
    )
    return identities


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--compose-file", default="compose.production.yml")
    parser.add_argument("--http-only", action="store_true")
    parser.add_argument("--check-restart", action="store_true")
    parser.add_argument("--probe-private-ports", action="store_true")
    args = parser.parse_args()
    if args.http_only and args.check_restart:
        parser.error(
            "Restart verification requires access to the deployed host's Docker"
        )
    run(
        args.url.rstrip("/"),
        args.docker,
        args.compose_file,
        args.http_only,
        args.check_restart,
        args.probe_private_ports,
    )
