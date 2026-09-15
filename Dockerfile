FROM python:3.11-slim

ARG INSTALL_LOCAL_MODELS=true

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models

WORKDIR /srv

COPY requirements.txt requirements-local.txt ./
RUN pip install -r requirements.txt \
    && if [ "$INSTALL_LOCAL_MODELS" = "true" ]; then \
         pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu \
         && pip install -r requirements-local.txt; \
       fi

RUN useradd --create-home app && mkdir -p /models && chown app /models
COPY alembic.ini .
COPY app app
USER app

EXPOSE 8000
CMD ["sh", "-c", "if [ -n \"$MIGRATION_DATABASE_URL\" ]; then alembic upgrade head; fi && exec uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
