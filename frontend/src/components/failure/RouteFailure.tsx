import { useRouteError } from "react-router";
import { FailureState } from "./FailureState";
import { clientFailure } from "@/lib/failures/resolve";

/** 路由加载失败显式标记来源，不根据浏览器异常文案猜测版本问题。 */
export function routeModule<T extends object>(load: () => Promise<T>) {
  return async () => {
    try {
      return await load();
    } catch {
      throw clientFailure("route_module_failed", "页面资源未能加载，请重新加载后再试。");
    }
  };
}

export function RouteFailure({ layout = "page" }: { layout?: "page" | "section" }) {
  const error = useRouteError();
  return (
    <FailureState
      error={error}
      layout={layout}
      context={{ operation: "render", resource: "page" }}
      actions={[
        { label: "重新加载", kind: "retry", onClick: () => window.location.reload() },
        { label: "返回员工目录", kind: "return", href: "/agents" },
      ]}
    />
  );
}

export function RouteNotFound() {
  return (
    <FailureState
      failure={{
        source: "client",
        status: null,
        code: "page_not_found",
        message: "请核对地址，或返回员工目录继续浏览。",
      }}
      layout="page"
      context={{ operation: "initial-read", resource: "page" }}
      actions={[{ label: "返回员工目录", kind: "return", href: "/agents" }]}
    />
  );
}
