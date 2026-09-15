import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
import openai
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langfuse import get_client

from app.api.routes import router
from app.auth.service import AuthError
from app.config import settings
from app.embeddings import get_model
from app.ingestion.extract import InvalidFileError, UnsupportedFileError
from app.retrieval.rerank import get_reranker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("groundline")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.preload_models:
        loaders = []
        if settings.embedding_provider == "local":
            loaders.append(asyncio.to_thread(get_model))
        if settings.rerank_provider == "local":
            loaders.append(asyncio.to_thread(get_reranker))
        await asyncio.gather(*loaders)
    yield
    get_client().shutdown()


app = FastAPI(title="Groundline", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


def _error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status_code)


@app.exception_handler(UnsupportedFileError)
async def unsupported_file(request: Request, exc: UnsupportedFileError) -> JSONResponse:
    return _error(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc))


@app.exception_handler(InvalidFileError)
async def invalid_file(request: Request, exc: InvalidFileError) -> JSONResponse:
    return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


@app.exception_handler(AuthError)
async def auth_error(request: Request, exc: AuthError) -> JSONResponse:
    return _error(status.HTTP_401_UNAUTHORIZED, str(exc))


@app.exception_handler(openai.APITimeoutError)
@app.exception_handler(httpx.TimeoutException)
async def provider_timeout(request: Request, exc: Exception) -> JSONResponse:
    log.warning("Model provider timeout: %s", exc)
    return _error(status.HTTP_504_GATEWAY_TIMEOUT, "Model provider timed out")


@app.exception_handler(openai.OpenAIError)
@app.exception_handler(httpx.HTTPError)
async def provider_unavailable(request: Request, exc: Exception) -> JSONResponse:
    log.warning("Model provider error: %s", exc)
    return _error(status.HTTP_502_BAD_GATEWAY, "Model provider unavailable")
