from fastapi import FastAPI

app = FastAPI(title="MicroTrace Notification Service")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
