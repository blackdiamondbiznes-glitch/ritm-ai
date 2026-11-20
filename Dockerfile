FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts
COPY entrypoint.sh .
RUN sed -i 's/\r$//' entrypoint.sh && chmod 755 entrypoint.sh scripts/*.py scripts/*.sh && chown -R appuser:appuser /app

USER appuser
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=5 CMD python scripts/healthcheck.py
ENTRYPOINT ["./entrypoint.sh"]
