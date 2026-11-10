from app.resources.mcp.models import ToolConnection


class WorkspaceProfile(ToolConnection):
    """仅保留历史原生连接的 ORM 读取映射，不再提供装配入口。"""

    __mapper_args__ = {"polymorphic_identity": "native"}
