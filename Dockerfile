FROM python:3.12-slim AS admin-build
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && rm -rf /var/lib/apt/lists/*
COPY admin-frontend/package.json admin-frontend/
RUN cd admin-frontend && npm install
COPY admin-frontend/ admin-frontend/
RUN cd admin-frontend && npm run build

FROM python:3.12-slim AS smc-build
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && rm -rf /var/lib/apt/lists/*
COPY smc-frontend/package.json smc-frontend/
RUN cd smc-frontend && npm install
COPY smc-frontend/ smc-frontend/
RUN cd smc-frontend && npm run build

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=admin-build /build/static/admin /app/static/admin
COPY --from=smc-build /build/static/app /app/static/app

VOLUME ["/app/data", "/app/model", "/app/logs", "/app/backups"]

EXPOSE 5000

CMD ["python", "run.py", "start", "--no-build"]
