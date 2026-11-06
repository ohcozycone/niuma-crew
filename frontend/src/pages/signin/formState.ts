import { ApiError } from "@/lib/api/http";
export type InvalidField = "username" | "password";

export function githubSigninFailure(code: string) {
  if (code === "github_cancelled") return "GitHub 登录已取消，可重新尝试。";
  if (code === "github_expired") return "登录请求已失效，请重新点击 GitHub 登录。";
  if (code === "github_account_disabled") return "当前账号已停用，请联系管理员。";
  if (code === "github_unavailable") return "GitHub 登录暂未启用，请使用其他入口。";
  if (code === "github_origin_mismatch") return "请从站点配置的地址访问后再登录。";
  if (code === "rate_limited") return "尝试过于频繁，请稍后再试。";
  return "暂时无法完成 GitHub 登录，请重试或使用其他入口。";
}
export function requiredCredentials(username: string, password: string) {
  const fields: InvalidField[] = [];
  if (!username.trim()) fields.push("username");
  if (!password) fields.push("password");
  return {
    fields,
    message:
      fields.length === 2
        ? "请输入用户名和密码。"
        : fields[0] === "username"
          ? "请输入用户名。"
          : fields[0] === "password"
            ? "请输入密码。"
            : "",
  };
}
/** Concise actionable feedback; no server internals in the reserved two lines. */
export function signinFailure(failure: unknown) {
  if (failure instanceof ApiError) {
    if (failure.code === "invalid_credentials") return "用户名或密码不正确，请重试。";
    if (failure.status === 429) return "尝试过于频繁，请稍后再试。";
    if (failure.status === 0 || failure.status >= 500) return "暂时无法连接服务，请稍后重试。";
    if (failure.status === 422) return "账号信息不符合要求，请检查后重试。";
    if (failure.status === 403) return "当前请求未获允许，请刷新页面重试。";
  }
  return "暂时无法登录，请稍后重试。";
}
