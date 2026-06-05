from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os

from server.routers import auth, pam, iam, reports, agents_ws, metrics, admin

app = FastAPI(title="PAM/IAM Testing Platform", version="1.0.0")

# Ensure static directories exist
os.makedirs("server/static/css", exist_ok=True)
os.makedirs("server/static/js", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="server/static"), name="static")

# Templates
templates = Jinja2Templates(directory="server/templates")

# Include routers
app.include_router(auth.router)
app.include_router(pam.router)
app.include_router(iam.router)
app.include_router(reports.router)
app.include_router(agents_ws.router)
app.include_router(metrics.router)
app.include_router(admin.router)

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    return templates.TemplateResponse("users.html", {"request": request})

@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    return templates.TemplateResponse("reports.html", {"request": request})

@app.get("/modules/pam/vaulting", response_class=HTMLResponse)
async def vaulting_page(request: Request):
    return templates.TemplateResponse("pam_vaulting.html", {"request": request})

@app.get("/modules/iam/sso", response_class=HTMLResponse)
async def sso_page(request: Request):
    return templates.TemplateResponse("iam_sso.html", {"request": request})
