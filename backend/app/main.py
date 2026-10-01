from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.workflows.routes import router as workflows_router
from app.ideas.routes import router as ideas_router
from app.sources.routes import router as sources_router
from app.publishing.routes import router as publications_router
from app.strategies.routes import router as strategies_router
from app.ideas.scout_provider import check_api_key_configuration


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_api_key_configuration()
    yield


app = FastAPI(title="Content OS", lifespan=lifespan)

# CORS middleware for local frontend development (Next.js default on localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workflows_router, prefix="/api")
app.include_router(ideas_router, prefix="/api")
app.include_router(sources_router, prefix="/api")
app.include_router(publications_router, prefix="/api")
app.include_router(strategies_router, prefix="/api")



@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1")).scalar_one()
    return {"status": "ok", "db_result": result}
