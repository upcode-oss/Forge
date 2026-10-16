from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import database
from app.api import router
from app.avatars import router as avatars_router
from app.config import settings
from app.git_http import router as git_router
from app.integrations import router as integrations_router
from app.organizations import router as organizations_router
from app.profiles import router as profiles_router
from app.ssh_keys import router as ssh_keys_router
from app.ssh_server import start_ssh_server


@asynccontextmanager
async def lifespan(app):
    config = settings()
    config.validate_secrets()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    database.load()
    ssh = await start_ssh_server() if config.ssh_enabled else None
    try:
        yield
    finally:
        if ssh:
            await ssh.close()
        if database.engine is not None:
            database.engine.dispose()
            database.engine = None


app = FastAPI(title="Upcode Forge", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def browser_security(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        # Requiring a custom header blocks cross-origin form submissions. No CORS is enabled.
        if request.headers.get("x-forge-request") != "1":
            return JSONResponse({"detail": "Missing request protection header"}, status_code=403)
        origin = request.headers.get("origin")
        allowed = {settings().bootstrap_origin.rstrip("/")}
        if database.engine is not None:
            from sqlalchemy.orm import Session

            from app.models import Instance

            with Session(database.engine) as db:
                allowed.add(db.get(Instance, 1).public_url)
        if origin and origin.rstrip("/") not in allowed:
            return JSONResponse({"detail": "Untrusted request origin"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = (
        "no-store"
        if request.url.path.startswith("/api/")
        else response.headers.get("Cache-Control", "no-cache")
    )
    return response


@app.get("/health")
def health():
    if database.engine is not None:
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    return {"status": "ok", "setup_completed": database.engine is not None}


app.include_router(router)
app.include_router(profiles_router)
app.include_router(avatars_router)
app.include_router(organizations_router)
app.include_router(ssh_keys_router)
app.include_router(integrations_router)
app.include_router(git_router)
