FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY racelens/ ./racelens/

RUN pip install --no-cache-dir -e ".[api]"

ENV RACELENS_FIXTURES=/data/fixtures

VOLUME /data

EXPOSE 8000

CMD ["uvicorn", "racelens.api:app", "--host", "0.0.0.0", "--port", "8000"]
