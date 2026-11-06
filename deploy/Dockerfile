FROM node:22-bookworm-slim AS frontend-build
WORKDIR /src/frontend
RUN npm install --global pnpm@11.11.0
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM node:22-bookworm-slim AS docs-build
WORKDIR /src
RUN npm install --global pnpm@11.11.0
COPY docs-site/package.json docs-site/pnpm-lock.yaml ./docs-site/
RUN cd docs-site && pnpm install --frozen-lockfile
COPY . .
COPY --from=frontend-build /src/frontend/public/brand ./frontend/public/brand
ARG DOCS_BASE_PATH=/docs
ARG PLATFORM_URL=http://127.0.0.1:3000
ENV NEXT_PUBLIC_DOCS_BASE_PATH=$DOCS_BASE_PATH
ENV NEXT_PUBLIC_PLATFORM_URL=$PLATFORM_URL
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_OPTIONS=--max-old-space-size=768
RUN cd docs-site && pnpm build

FROM python:3.12-slim-bookworm AS app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1
ENV PYTHONUNBUFFERED=1 ANONYMIZED_TELEMETRY=False
WORKDIR /app/backend
RUN pip install --no-cache-dir uv==0.12.7 \
    && useradd --uid 10001 --create-home niuma \
    && mkdir /data && chown niuma:niuma /data
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY backend/datasets/travel-expense ./datasets/travel-expense
COPY --from=frontend-build /src/frontend/dist /app/frontend/dist
COPY deploy/start-app.sh /app/start-app.sh
ENV PATH=/app/backend/.venv/bin:$PATH
ENV APP_DATA_DIR=/data SKILL_LIBRARY_DIR=/data/skill-library
USER niuma
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/ready', timeout=4)"
ENTRYPOINT ["sh", "/app/start-app.sh"]

FROM nginx:stable-alpine AS docs
COPY deploy/docs.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=docs-build /src/docs-site/out /usr/share/nginx/html/docs
EXPOSE 3001
HEALTHCHECK --interval=30s --timeout=5s \
  CMD wget --spider -q http://127.0.0.1:3001/docs/
