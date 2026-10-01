"""Run from the trace-backend container to check the four real HTTP health endpoints."""

import json
from urllib.request import urlopen


def main() -> None:
    for service in (
        "order-service",
        "payment-service",
        "notification-service",
        "trace-backend",
    ):
        with urlopen(f"http://{service}:8000/health", timeout=5) as response:
            assert response.status == 200, service
            assert json.load(response) == {"status": "ok"}, service
        print(f"{service}: health PASS")


if __name__ == "__main__":
    main()
