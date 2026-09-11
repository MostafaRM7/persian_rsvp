"""Persian RSVP Speed Reader — FastAPI backend with Tortoise ORM and JWT Authentication."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from tortoise.contrib.fastapi import register_tortoise

from config import BASE_DIR
from database import TORTOISE_ORM
from routers.auth import router as auth_router
from routers.rsvp import router as rsvp_router
from routers.texts import router as texts_router

app = FastAPI(
    title="Persian RSVP Speed Reader",
    description="تندخوان هوشمند فارسی (RSVP) با احراز هویت JWT و پایگاه داده Tortoise ORM",
    version="1.0.0",
)

# Include API routers
app.include_router(auth_router)
app.include_router(rsvp_router)
app.include_router(texts_router)

# Mount static assets
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")


# Register Tortoise ORM
register_tortoise(
    app,
    config=TORTOISE_ORM,
    generate_schemas=True,
    add_exception_handlers=True,
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
