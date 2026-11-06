import { useEffect, useEffectEvent, useState } from "react";
import { useSearchParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ConfirmActionDialog } from "@/components/common/ConfirmActionDialog";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { clientFailure, toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import {
  cancelToolOAuth,
  disconnectToolOAuth,
  discoverTools,
  listToolConnections,
  readToolOAuth,
  startToolOAuth,
  type ToolConnection,
} from "@/lib/api/tools";

export function OAuthConnectionPanel({
  connection,
  onChange,
}: {
  connection: ToolConnection;
  onChange: (value: ToolConnection) => void;
}) {
  const [params, setParams] = useSearchParams();
  const [session, setSession] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [notice, setNotice] = useState("");
  const [confirm, setConfirm] = useState<"connect" | "disconnect" | null>(null);
  const returnSession =
    params.get("oauth_connection") === connection.id ? params.get("oauth_session") : null;
  const autoConnect = params.get("oauth_connect") === connection.id;
  const clearQuery = useEffectEvent(() => {
    const next = new URLSearchParams(params);
    for (const key of ["oauth_connection", "oauth_session", "oauth_connect"]) next.delete(key);
    setParams(next, { replace: true });
  });
  const changed = useEffectEvent((value: ToolConnection) => onChange(value));
  const begin = useEffectEvent(async () => {
    const result = await startToolOAuth(connection);
    setSession(result.id);
  });
  useEffect(() => {
    if (!autoConnect) return;
    let stopped = false;
    void begin()
      .catch((error) => {
        if (!stopped) setFailure(toFailure(error));
      })
      .finally(() => {
        if (!stopped) clearQuery();
      });
    return () => {
      stopped = true;
    };
  }, [autoConnect]);
  useEffect(() => {
    const id = session ?? returnSession;
    if (!id) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await readToolOAuth(connection.id, id!, controller.signal);
        if (controller.signal.aborted) return;
        if (result.status === "awaiting_consent" && result.authorization_url) {
          window.location.assign(result.authorization_url);
          return;
        }
        if (["preparing", "exchanging"].includes(result.status)) {
          timer = setTimeout(() => void poll(), 750);
          return;
        }
        const values = await listToolConnections(controller.signal);
        const current = values.find((value) => value.id === connection.id);
        if (current) changed(current);
        if (result.status === "succeeded") {
          setNotice("账号已连接，正在读取工具列表…");
          const discovered = await discoverTools(connection.id);
          if (!controller.signal.aborted) {
            changed(discovered);
            setNotice("工具列表已读取，请确认后到员工页面装配。");
          }
        } else {
          throw clientFailure(
            result.error_code ?? "oauth_failed",
            result.error_message ?? "授权未完成，请重新连接账号。",
          );
        }
        setSession(null);
        clearQuery();
      } catch (error) {
        if (!controller.signal.aborted) {
          setFailure(toFailure(error));
          setNotice("");
          setSession(null);
          clearQuery();
        }
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [connection.id, returnSession, session]);
  async function connect() {
    setBusy(true);
    setFailure(null);
    setNotice("");
    try {
      const result = await startToolOAuth(connection);
      setSession(result.id);
      setConfirm(null);
    } catch (error) {
      setFailure(toFailure(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-3">
      <p className="type-caption" role="status">
        {session || returnSession
          ? "正在连接账号…"
          : connection.oauth_status === "connected"
            ? "OAuth 账号已连接"
            : connection.oauth_status === "reauth_required"
              ? "授权已失效，请重新连接账号。"
              : "尚未连接账号。点击后前往服务方登录并授权。"}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={busy || !!session || !!returnSession || !connection.enabled}
          onClick={() =>
            connection.oauth_status === "connected" ? setConfirm("connect") : void connect()
          }
        >
          {connection.oauth_status === "connected" ? "重新连接账号" : "连接账号"}
        </Button>
        {(session || returnSession) && (
          <Button
            type="button"
            variant="ghost"
            onClick={async () => {
              try {
                await cancelToolOAuth(connection.id, (session ?? returnSession)!);
                const values = await listToolConnections();
                const current = values.find((value) => value.id === connection.id);
                if (current) onChange(current);
                setSession(null);
                const next = new URLSearchParams(params);
                for (const key of ["oauth_connection", "oauth_session", "oauth_connect"])
                  next.delete(key);
                setParams(next, { replace: true });
                setNotice("已取消授权。");
              } catch (error) {
                setFailure(toFailure(error));
              }
            }}
          >
            取消授权
          </Button>
        )}
        {connection.oauth_status === "connected" && (
          <Button
            type="button"
            variant="ghost"
            disabled={busy}
            onClick={() => setConfirm("disconnect")}
          >
            断开账号
          </Button>
        )}
      </div>
      {notice && (
        <p className="type-caption" role="status">
          {notice}
        </p>
      )}
      <FailureNotice
        failure={failure}
        context={{ operation: "mutation", resource: "connection" }}
      />
      <ConfirmActionDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!open) setConfirm(null);
        }}
        title={confirm === "disconnect" ? "断开账号？" : "重新连接账号？"}
        description="当前授权和旧运行依据将失效，后续需要重新读取并确认工具列表。"
        confirmLabel={confirm === "disconnect" ? "断开账号" : "重新连接"}
        busy={busy}
        onConfirm={() => {
          if (confirm === "connect") void connect();
          else {
            setBusy(true);
            void disconnectToolOAuth(connection)
              .then((value) => {
                onChange(value);
                setConfirm(null);
              })
              .catch((error) => setFailure(toFailure(error)))
              .finally(() => setBusy(false));
          }
        }}
      />
    </div>
  );
}
