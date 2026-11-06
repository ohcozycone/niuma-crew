import type { Failure } from "@/lib/failures/types";
import { toFailure, clientFailure } from "@/lib/failures/resolve";
import { useEffect } from "react";
import { ApiError } from "@/lib/api/http";
import { isObserving, type Reply } from "@/lib/api/conversations";
import type { ConversationTransport } from "@/lib/api/conversationTransport";
import type { ConversationError } from "./conversationState";

/** 只观察一个 Reply；订阅和重连都不会接受工作。 */
export function useResponseSubscription(
  conversationId: string,
  runId: string | null,
  transport: ConversationTransport,
  onSnapshot: (run: Reply) => void,
  onError: (error: ConversationError | null) => void,
  reconnectVersion: number,
) {
  useEffect(() => {
    if (!runId) return;
    let disposed = false;
    let finished = false;
    let recovering = false;
    let failures = 0;
    let highestRevision = -1;
    let close: (() => void) | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const end = () => {
      close?.();
      close = undefined;
      if (timer) clearTimeout(timer);
    };
    function receive(run: Reply) {
      if (disposed || finished || run.id !== runId || run.version < highestRevision) return;
      if (run.version > highestRevision) {
        failures = 0;
        highestRevision = run.version;
      }
      onError(null);
      onSnapshot(run);
      if (!isObserving(run)) {
        finished = true;
        end();
      }
    }
    function schedule(failure?: Failure | null) {
      if (disposed || finished) return;
      failures += 1;
      if (failures > 3) {
        onError({
          message: "连接中断；执行可能仍在继续，请重新连接查看。",
          failure:
            failure ??
            clientFailure(
              "client_stream_disconnected",
              "连接中断；执行可能仍在继续，请重新连接查看。",
            ),
          recovery: "reconnect",
        });
        return;
      }
      onError({
        message: "连接恢复中，执行可能仍在继续…",
        failure:
          failure ?? clientFailure("client_stream_disconnected", "连接恢复中，执行可能仍在继续…"),
        recovery: null,
      });
      timer = setTimeout(connect, [1000, 2000, 5000][failures - 1]);
    }
    async function recover() {
      if (disposed || finished || recovering) return;
      recovering = true;
      end();
      try {
        const run = await transport.getResponse(conversationId, runId!, controller.signal);
        if (disposed) return;
        receive(run);
        schedule();
      } catch (error) {
        if (disposed) return;
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
          finished = true;
          onError({
            message: toFailure(error)?.message ?? "",
            failure: toFailure(error),
            recovery: null,
          });
        } else schedule(toFailure(error));
      } finally {
        recovering = false;
      }
    }
    function connect() {
      if (disposed || finished) return;
      end();
      close = transport.subscribe(conversationId, runId!, {
        snapshot: receive,
        disconnected: () => {
          void recover();
        },
        invalid: () => {
          finished = true;
          end();
          onError({
            message: "响应无法识别，请重新连接。",
            failure: clientFailure("client_stream_disconnected", "响应无法识别，请重新连接。"),
            recovery: "reconnect",
          });
        },
        revoked: () => {
          finished = true;
          end();
          onError({
            message: "会话或访问权限需重新确认。",
            failure: clientFailure("permission_denied", "会话或访问权限需重新确认。"),
            recovery: null,
          });
        },
      });
      if (finished) end();
    }
    connect();
    return () => {
      disposed = true;
      controller.abort();
      end();
    };
  }, [conversationId, runId, transport, onSnapshot, onError, reconnectVersion]);
}
