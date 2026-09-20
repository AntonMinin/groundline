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
COPY scripts/start.sh scripts/start.sh
RUN chmod +x scripts/start.sh
USER app

EXPOSE 8000
CMD ["./scripts/start.sh"]
