ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE}
WORKDIR /work
COPY api/requirements.txt /tmp/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r /tmp/requirements.txt pytest==8.4.1 httpx==0.28.1 lxml==6.0.0 && useradd --uid 10001 --create-home tester
# The whole project (see .dockerignore: no .env, local/, backups): tests also read scripts/, systemd/,
# docs/openapi.json, package.json, README.md and UPDATE-INFO.md.
COPY . /work
COPY db/legacy-seed.json /opt/killstass/seed.json
ENV PYTHONPATH=/work PYTHONDONTWRITEBYTECODE=1
USER 10001
ENTRYPOINT ["python","-m","pytest","-q","-p","no:cacheprovider","tests"]
