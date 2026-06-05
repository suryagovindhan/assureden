"""server/main.py — AssureDen FastAPI application entry point"""
import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from server.routers import auth, admin, reports, metrics, agents_ws, sandbox_ws

app = FastAPI(title="AssureDen", version="1.0.0", description="PAM/IAM Enterprise Testing Platform")

# ── Static files & templates ─────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(_HERE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_HERE, "templates"))

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(reports.router)
app.include_router(metrics.router)
app.include_router(agents_ws.router)
app.include_router(sandbox_ws.router)

# ── HTML page routes ──────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    return templates.TemplateResponse("reports.html", {"request": request})

@app.get("/sandbox", response_class=HTMLResponse)
async def sandbox_page(request: Request):
    return templates.TemplateResponse("sandbox.html", {"request": request})
