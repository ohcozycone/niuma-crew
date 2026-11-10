from app.errors import NotFoundError
from app.mcp.models import McpService, ToolConnection


def managed_connection(db, id: str) -> ToolConnection:
    row = db.get(ToolConnection, id)
    if row is None or row.kind == "native":
        raise NotFoundError("tool_connection_not_found", "工具连接不存在。")
    return row


def service_manager(db, id: str) -> McpService:
    row = db.get(McpService, id)
    if row is None:
        raise NotFoundError("mcp_service_not_found", "MCP 服务不存在或无权管理。")
    return row
