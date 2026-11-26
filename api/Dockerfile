ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home app
COPY VERSION /app/VERSION
COPY api /app/api
COPY web /app/web
USER 10001
EXPOSE 8000
CMD ["uvicorn","api.main:app","--host","0.0.0.0","--port","8000","--workers","1","--no-access-log","--no-proxy-headers","--limit-concurrency","256","--backlog","128"]
