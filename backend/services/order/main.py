from fastapi import FastAPI

app = FastAPI(title="MicroTrace Order Service")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
