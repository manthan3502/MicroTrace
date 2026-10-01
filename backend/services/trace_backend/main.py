from fastapi import FastAPI, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from services.trace_backend.database import check_database
from services.trace_backend.ingest import router as ingest_router


def create_app() -> FastAPI:
    app = FastAPI(title="MicroTrace Backend")
    app.include_router(ingest_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        try:
            check_database()
        except (SQLAlchemyError, RuntimeError):
            raise HTTPException(status_code=503, detail="Database unavailable") from None
        return {"status": "ok"}

    return app


app = create_app()
