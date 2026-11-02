## `PinnedTransport.handle_async_request` in backend/app/tools/network.py (L61-L108)

**Purpose:** 每个 MCP HTTP 请求在发送前核对目标、解析地址并固定本次 IP，响应在协议解析之前限量。

**Inputs & Assumptions:**

- `request`：SDK 构建，包含账号认证头，semi-trusted；目标必须匹配构造时 `validate_endpoint` 认可的 host/port/scheme（L55-L59）。
- DNS 回答：不可信，L80-L93 检查每个地址。
- config 由部署者控制；仅 exact `private_hosts` 可允许私网，link-local/multicast/unspecified 仍拒绝。

**Outputs & Effects:**

- 发出至首个认可 IP 的网络请求，保留原 Host 与 TLS SNI；返回包裹后的 httpx Response。
- 域名解析错误转换为平台公开错误；没有自行重试（L59）。

**Block-by-Block:**

```python
# L62-L68
port = request.url.port or (443 if request.url.scheme == "https" else 80)
# host、port、scheme 必须与登记目标一致。
```

- **What:** 阻止 SDK 请求换主机、换端口或协议。
- **Why here:** 在 DNS 及发送认证头之前拒绝。
- **Assumes:** SDK 同站点请求路径属于已登记服务；没有限定原 path（L64-L66）。
- **Establishes:** 所有后续请求都维持相同 origin。
- **Depended on by:** DNS、认证头转发。

```python
# L70-L88
answers = await asyncio.get_running_loop().getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
# 对全部回答验证 ip 的公开性及私网名单。
```

- **What:** 获取并检查实际连接地址。
- **Why here:** 不仅保存时检查 URL，运行时也检查当前 DNS。
- **Assumes:** getaddrinfo 取消后线程的最终退出由 asyncio 负责；本函数没有独立总超时。
- **Establishes:** 仅被认可的实际地址可进入发送阶段。
- **Depended on by:** L96 把 URL host 改成首个实际 IP。

```python
# L94-L107
pinned = httpx.Request(..., extensions={**request.extensions, "sni_hostname": self.host})
response = await self.inner.handle_async_request(pinned)
response.stream = BoundedStream(response.stream, self.config.max_response_bytes)
```

- **What:** 原 Host/SNI 与固定 IP 协作；非 identity 压缩在 L102-L106 被关闭并拒绝。
- **Why here:** 避免认证请求重新解析跳入私网，以及压缩后无界解压。
- **Assumes:** httpx 接受保留 Host + sni_hostname 的语义，由 test_agent_foundations DNS/TLS 及 test_mcp_accounts 私网测试验证。
- **Establishes:** 每个 HTTP response stream 的读取上限，超出在 BoundedStream L42-L48 拒绝。
- **Depended on by:** MCPClient `_tools` / `invoke` 的协议解析。

**Cross-Function Dependencies:**

- `validate_endpoint`（internal，L14-L35）：拒绝 URL 内秘密、查询及 fragment，并核对部署主机。
- `BoundedStream`（internal，L38-L51）：原始流逐块计数，`aclose` 委托释放。
- httpx transport（external-source-available）：处理 TLS 与连接；`MCPClient.session` L75-L91 关闭环境代理/重定向，设置请求时限。
- Caller：`_ErrorRecordingTransport.handle_async_request` 保存平台错误，防止 SDK 包装后丢掉诊断。

**Open Questions:**

- 真实部署 DNS/TLS/上游连接可用性未访问真实服务，离线替身不能回答。
