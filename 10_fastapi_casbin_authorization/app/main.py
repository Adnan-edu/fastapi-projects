from fastapi import FastAPI

from app.api.routes_documents import router as documents_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="FastAPI Casbin Authorization - Document Management API",
        description="Learn RBAC/ABAC authorization in FastAPI using Casbin",
        version="0.1.0",
    )

    @app.get("/health", tags=["health"], include_in_schema=False)
    def health():
        return {"status": "ok"}

    app.include_router(documents_router)

    return app


app = create_app()