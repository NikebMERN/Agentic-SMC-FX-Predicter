FROM python:3.12-slim AS admin-build
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && rm -rf /var/lib/apt/lists/*
COPY admin-frontend/package.json admin-frontend/
COPY admin-frontend/package-lock.json admin-frontend/
RUN cd admin-frontend && npm ci
COPY admin-frontend/ admin-frontend/
RUN cd admin-frontend && npm run build

FROM python:3.12-slim AS smc-build
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && rm -rf /var/lib/apt/lists/*
COPY smc-frontend/package.json smc-frontend/
COPY smc-frontend/package-lock.json smc-frontend/
RUN cd smc-frontend && npm ci
COPY smc-frontend/ smc-frontend/
RUN cd smc-frontend && npm run build

FROM python:3.12-slim

WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=admin-build /build/static/admin /app/static/admin
COPY --from=smc-build /build/static/app /app/static/app

EXPOSE 5000

CMD ["gunicorn", "--config", "deploy/gunicorn.conf.py", "app:app"]
