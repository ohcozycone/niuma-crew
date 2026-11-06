import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/http";
import { githubSigninFailure, requiredCredentials, signinFailure } from "./formState";
describe("signin feedback", () => {
  it("marks only missing credentials and preserves meaningful password whitespace", () => {
    expect(requiredCredentials("", "").fields).toEqual(["username", "password"]);
    expect(requiredCredentials("  ", "secret").fields).toEqual(["username"]);
    expect(requiredCredentials("admin", "").message).toBe("请输入密码。");
    expect(requiredCredentials("admin", " ").fields).toEqual([]);
  });
  it("maps credentials, rate limiting and unavailable service without server internals", () => {
    expect(signinFailure(new ApiError("raw", 401, "invalid_credentials"))).toBe(
      "用户名或密码不正确，请重试。",
    );
    expect(signinFailure(new ApiError("raw", 429))).toContain("稍后");
    expect(signinFailure(new ApiError("raw", 502))).toContain("连接");
    expect(signinFailure(new Error("internal details"))).not.toContain("internal");
  });
  it("explains OAuth failures using fixed messages without reflecting query content", () => {
    expect(githubSigninFailure("github_cancelled")).toContain("取消");
    expect(githubSigninFailure("github_expired")).toContain("重新点击");
    expect(githubSigninFailure("github_account_disabled")).toContain("停用");
    expect(githubSigninFailure("github_unavailable")).toContain("其他入口");
    expect(githubSigninFailure("rate_limited")).toContain("稍后");
    expect(githubSigninFailure("<script>secret</script>")).not.toContain("secret");
  });
});
