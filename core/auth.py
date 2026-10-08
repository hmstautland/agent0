from os import getenv

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.templates import templates

PASSWORD = getenv("APP_LOGIN_PASSWORD")


async def is_logged_in(request: Request):
    if not request.session.get("authenticated") == True:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return request


public_router = APIRouter()


@public_router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if not await is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse(name="index.html", request=request, context={"response": ""})


@public_router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(name="login.html", request=request, context={
        "error": None
    })


@public_router.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == PASSWORD:
        request.session["authenticated"] = True
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(name="login.html", request=request, context={
        "error": "Invalid password"
    })


# Catch-all route for undefined paths - must be registered last, after every
# other router, or it will shadow their routes.
@public_router.get("/{full_path:path}")
async def catch_all(request: Request, full_path: str):
    if request.session.get("authenticated") == True:
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


logout_router = APIRouter(dependencies=[Depends(is_logged_in)])


@logout_router.get("/logout")
def logout_page(request: Request):
    return templates.TemplateResponse(name="logout.html", request=request, context={
        "error": None
    })


@logout_router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
