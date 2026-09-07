"""Render 单容器入口：同源挂载 API 与 PWA 静态产物。"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles


DATA_DIR = Path(os.getenv("BANGBANG_DATA_DIR", "/tmp/bangbang-data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("BANGBANG_DB_PATH", str(DATA_DIR / "bangbang.db"))
os.environ.setdefault("BANGBANG_UPLOAD_DIR", str(DATA_DIR / "uploads"))

render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_hostname:
    os.environ["BANGBANG_ALLOWED_HOSTS"] = render_hostname

from main import app as api_app  # noqa: E402


STATIC_DIR = Path(os.getenv("BANGBANG_STATIC_DIR", "/app/static"))


class SPAStaticFiles(StaticFiles):
    """静态资源不存在时仅为前端路由回退到 index.html。"""

    async def get_response(self, path: str, scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or "." in Path(path).name:
                raise
            return FileResponse(STATIC_DIR / "index.html")
        if response.status_code == 404 and "." not in Path(path).name:
            return FileResponse(STATIC_DIR / "index.html")
        return response


app = FastAPI(
    title="帮帮师记公开体验版",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def public_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


app.mount("/api", api_app)
app.mount("/", SPAStaticFiles(directory=STATIC_DIR, html=True), name="pwa")
