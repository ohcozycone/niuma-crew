# 项目运行脚本

本目录维护跨前后端的本地运行与进程管理，由根 [Makefile](../Makefile) 调用。前端资源构建仍在 [frontend/scripts](../frontend/scripts/README.md)。

[dev.py](dev.py) 使用后端 Python 环境，以 `app.main:app` 加载应用，持有后端监听套接字直到交给 Uvicorn，并向 Vite 注入实际代理地址。每个服务拥有独立进程组，启动失败、任一服务退出或终端中断时统一清理；不改写 `.env`，不接管既有服务。

启动器行为通过 `make test-dev` 验证，代码风格由 `make lint-backend` 检查。流程、参数和验收见[本地开发设计](../docs/guides/local-development.md)。

## 文档检查

[check_docs.py](check_docs.py)由 `make check-docs` 调用，并已接入 `make check`。离线核对 Markdown 本地文件、章节锚点以及 docs 正文从索引的可达性，忽略代码示例与外网链接。主工程中的模块说明与教学资料也检查链接，但不改写资料内容。

归档是可选历史材料，默认仅统计其链接；需要核对本机归档时执行 `cd backend && uv run python ../scripts/check_docs.py --check-archive`。这属于专项脚本参数，主工程无需归档目录也能完成默认检查。脚本不验证外网可用性、业务语义、Markdown 排版或浏览器视觉。

解析和导航边界由[检查器测试](tests/test_check_docs.py)覆盖，包含中文/重复标题、显式锚点、示例代码、引用式目标、缺失文件与章节、索引不可达及可选归档。
