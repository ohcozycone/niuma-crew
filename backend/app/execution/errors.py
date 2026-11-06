"""Stable execution failures shared by the runner, SDK adapters and application code."""

from app.execution.contracts import RuntimeFailure

ExecutionFailure = RuntimeFailure

ERROR_MESSAGES = {
    "knowledge_access_revoked": "知识库装配、访问权限或来源已变化，请重新发送任务。",
    "knowledge_citation_invalid": "回答包含无法核对的知识来源，未发布成功结果，请重试。",
    "knowledge_source_changed": "知识来源已更新或删除，请重新检索。",
    "knowledge_owner_mismatch": "个人知识库不能用于他人拥有的对话。",
    "knowledge_evidence_not_found": "该来源不属于本轮检索结果，请重新检索。",
    "checkpoint_unavailable": "执行恢复资料缺失或不可读，请发起新的重试。",
    "skill_not_allowed": "技能不在本次获准目录内。",
    "skill_not_ready": "所选技能尚未就绪。",
    "skill_access_revoked": "技能已停用或装配已改变，执行已停止。",
    "agent_budget_exceeded": "已达到模型、技能读取或工具调用上限，请缩小任务范围。",
    "tool_not_allowed": "工具不在本轮许可范围内。",
    "tool_access_revoked": "工具许可、连接或凭证已改变，执行已停止。",
    "tool_catalog_changed": "远端工具目录已改变，请管理员重新审核。",
    "tool_upstream_failed": "工具服务调用失败，未取得已确认结果。",
    "tool_credentials_unavailable": "工具凭证不可用，请检查对应加密主密钥。",
    "tool_result_unknown": "工具结果无法确认，未自动重放。",
    "tool_result_too_large": "工具响应超过接收或保存上限。",
    "tool_arguments_invalid": "工具参数不符合已批准定义或范围。",
    "tool_url_denied": "网页地址不属于获准公开范围。",
    "file_path_denied": "文件路径不在本轮许可范围内。",
    "file_readonly": "输入、来源和技能目录只读。",
    "file_too_large": "文件超过当前工作区大小上限。",
    "file_quota_exceeded": "工作文件数量或总量超过上限。",
    "file_integrity_failed": "工作文件完整性校验失败。",
    "sandbox_not_ready": "沙箱尚未配置或完成目标主机验收。",
    "sandbox_capacity_exceeded": "沙箱资源占用或仍待清理，请稍后重试。",
    "sandbox_stop_failed": "未能确认沙箱工作负载停止，未发布结果。",
    "output_collection_failed": "输出文件未能可靠收集，未发布成功结果。",
    "skill_load_failed": "技能正文未能完整加载，执行已停止。",
    "agent_inactive": "员工已停用，请启用后重试。",
    "model_credentials_unavailable": "模型凭证不可用，请检查服务器加密密钥。",
    "model_configuration_changed": "排队期间大脑配置已更改，请重试。",
    "upstream_auth_failed": "模型凭证无效，请检查大脑配置。",
    "upstream_forbidden": "模型服务拒绝访问，请检查订阅与客户端使用权限。",
    "upstream_rate_limited": "模型服务限流，请稍后重试。",
    "context_limit_exceeded": "上下文超过模型限制，请开始新对话。",
    "upstream_unavailable": "暂时无法连接模型服务，请稍后重试。",
    "upstream_stream_error": "模型响应异常中断，请重试。",
    "empty_response": "模型未返回可见文本，请重试。",
    "external_read_unverified": "尚未取得并读取目标网页的提取结果，未发布模型声称的读取结论。请检查工具、账号或缩小读取范围后重试。",
    "output_limit_exceeded": "回答达到输出限制。",
    "run_timeout": "模型执行超时。",
    "execution_failed": "执行发生异常，请重试。",
    "sdk_stream_invalid": "模型消息与执行步骤不匹配，执行已停止。",
    "queue_timeout": "等待执行超时，请重试。",
    "actor_session_invalid": "发起会话已失效，执行已停止。",
    "runtime_interrupted": "服务中断，执行未自动重放，可手动重试。",
    "persistence_unavailable": "结果保存失败，执行已停止。",
}


class PersistenceFailure(Exception):
    """A rolled-back result transaction must stop all further actions."""


def terminal_status(code: str) -> str:
    if code in ("user_cancelled", "actor_session_invalid"):
        return "cancelled"
    if code in ("runtime_interrupted", "checkpoint_unavailable"):
        return "interrupted"
    return "failed"
