# 在仓库根目录执行；make help 查看公共命令。端内包脚本与 CLI 提供底层实现。
.DEFAULT_GOAL := help
export BACKEND_PORT ?= 8000
export BACKEND_URL ?= http://127.0.0.1:$(BACKEND_PORT)
export START_PORT ?= 3000
export DEV_TIMEOUT ?= 30
export ADMIN_USER ?= admin
export MIGRATION_MESSAGE ?=
.PHONY: help setup setup-backend setup-frontend dev dev-backend dev-frontend start preview build build-brand build-avatar-manifest check lint lint-backend lint-frontend lint-frontend-scripts typecheck format format-check test test-backend test-frontend test-dev test-avatars db-upgrade db-current db-check db-revision admin-create admin-reset-password admin-disable admin-enable admin-revoke-sessions admin-cleanup-sessions

help: ## 显示公共命令及作用
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  make %-24s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: setup-backend setup-frontend setup-docs ## 按锁文件安装依赖；仅在缺失时创建后端 .env
	@test -e backend/.env || (umask 077; cp -n backend/.env.example backend/.env)

setup-backend: ## 按锁文件安装后端依赖
	cd backend && uv sync --locked

setup-frontend: ## 按锁文件安装前端依赖
	cd frontend && pnpm install --frozen-lockfile

.PHONY: setup-docs dev-docs build-docs preview-docs check-docs-site
setup-docs: ## 安装独立文档站依赖
	cd docs-site && pnpm install --frozen-lockfile

dev-docs: ## 启动文档站与原文监听；固定 3001
	cd docs-site && pnpm dev

build-docs: ## 同步原文并构建静态文档站到 docs-site/out
	cd docs-site && pnpm build

preview-docs: ## 在 3001 预览已构建文档站
	cd docs-site && pnpm preview

check-docs-site: ## 检查文档站内容、类型、测试、格式和静态构建
	cd docs-site && pnpm check

dev: ## 启动完整开发环境；后端端口避让、代理联动、退出清理
	cd backend && exec uv run python ../scripts/dev.py --backend-port "$$BACKEND_PORT" --startup-timeout "$$DEV_TIMEOUT"

dev-backend: ## 单独启动后端热重载；固定 BACKEND_PORT，默认 8000
	cd backend && exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$$BACKEND_PORT" --no-proxy-headers --reload

dev-frontend: ## 单独启动前端；固定 3000，使用 BACKEND_URL
	cd frontend && exec pnpm dev --host 127.0.0.1 --port 3000 --strictPort

start: ## 启动后端同源交付；需先 make build 和数据库迁移
	@test -f frontend/dist/index.html || { echo '请先执行 make build。' >&2; exit 2; }
	cd backend && exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$$START_PORT" --no-proxy-headers

preview: ## 仅预览前端静态产物，不提供 API
	cd frontend && exec pnpm preview --host 127.0.0.1 --port 3000 --strictPort

build: ## 构建前端生产产物，不启动服务
	cd frontend && pnpm build

build-brand: ## 生成前端品牌资源
	cd frontend && pnpm build:brand

build-avatar-manifest: ## 生成头像清单快照
	cd frontend && pnpm build:avatar-manifest

check: ## 顺序执行文档、全项目检查、离线测试与生产构建
	$(MAKE) check-docs
	$(MAKE) check-docs-site
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) build

lint: lint-backend lint-frontend ## 前后端静态、类型和格式检查

lint-backend: ## 检查后端与共享运行脚本的静态规则、格式
	cd backend && uv run ruff check --config pyproject.toml . ../scripts
	cd backend && uv run ruff format --check --config pyproject.toml . ../scripts
	$(MAKE) typecheck-backend

.PHONY: typecheck-backend
typecheck-backend: ## 检查执行契约、准入、读取、请求服务与发布的 Python 类型
	cd backend && uv run mypy

.PHONY: check-docs
check-docs: ## 离线检查文档路径、章节与索引可达性；历史归档可选
	cd backend && uv run python ../scripts/check_docs.py

lint-frontend: ## 前端 ESLint、类型和格式检查
	cd frontend && pnpm lint && pnpm typecheck && pnpm format:check

lint-frontend-scripts: ## 单独检查前端构建脚本
	cd frontend && pnpm lint:scripts

typecheck: ## 单独执行前端类型检查
	cd frontend && pnpm typecheck

format: ## 格式化后端、共享运行脚本与前端
	cd backend && uv run ruff format --config pyproject.toml . ../scripts
	cd frontend && pnpm format

format-check: ## 只检查格式，不修改文件
	cd backend && uv run ruff format --check --config pyproject.toml . ../scripts
	cd frontend && pnpm format:check

test: ## 前后端及开发启动器离线测试，不调用真实模型
	$(MAKE) test-backend
	$(MAKE) test-frontend
	$(MAKE) test-dev

test-backend: ## 运行后端离线测试
	cd backend && uv run pytest

test-frontend: ## 运行前端离线测试
	cd frontend && pnpm test

test-dev: ## 验证端口避让、代理联动和进程清理
	cd backend && uv run pytest ../scripts/tests

test-avatars: ## 单独运行静态头像测试
	cd frontend && pnpm test:avatars

db-upgrade: ## 将当前配置的数据库升级至迁移 head
	cd backend && uv run alembic upgrade head

db-current: ## 查看当前数据库迁移版本
	cd backend && uv run alembic current

db-check: ## 检查数据库与迁移、模型定义是否一致
	cd backend && uv run alembic check

db-revision: ## 生成待审核迁移；需 MIGRATION_MESSAGE="描述"
	@test -n "$$MIGRATION_MESSAGE" || { echo '请提供 MIGRATION_MESSAGE。' >&2; exit 2; }
	cd backend && uv run alembic revision --autogenerate -m "$$MIGRATION_MESSAGE"

admin-create: ## 初始化管理员，ADMIN_USER 默认 admin；终端输入密码
	cd backend && uv run python -m app.auth.cli create-admin -- "$$ADMIN_USER"

admin-reset-password: ## 重置管理员密码并撤销旧会话
	cd backend && uv run python -m app.auth.cli reset-password -- "$$ADMIN_USER"

admin-disable: ## 停用管理员并撤销旧会话
	cd backend && uv run python -m app.auth.cli disable-user -- "$$ADMIN_USER"

admin-enable: ## 启用管理员并撤销旧会话
	cd backend && uv run python -m app.auth.cli enable-user -- "$$ADMIN_USER"

admin-revoke-sessions: ## 撤销指定管理员的会话
	cd backend && uv run python -m app.auth.cli revoke-sessions -- "$$ADMIN_USER"

admin-cleanup-sessions: ## 清理失效会话，不依赖 ADMIN_USER
	cd backend && uv run python -m app.auth.cli cleanup-sessions
