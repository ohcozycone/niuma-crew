"""Account ownership is independent of application administrator privileges."""

from app.errors import NotFoundError
from app.mcp.models import McpService, ToolConnection


def own_connection(db, id: str, user_id: str) -> ToolConnection:
    row = db.get(ToolConnection, id)
    if row is None or row.created_by_user_id != user_id:
        raise NotFoundError("tool_connection_not_found", "工具连接不存在。")
    return row


def service_manager(db, id: str, user_id: str) -> McpService:
    row = db.get(McpService, id)
    if row is None or row.owner_user_id != user_id:
        raise NotFoundError("mcp_service_not_found", "MCP 服务不存在或无权管理。")
    return row
