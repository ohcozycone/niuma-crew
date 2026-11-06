import { useEffect, useState } from "react";
import { ApiError, request } from "@/lib/api/http";
import { identityKey, type Identity } from "@/lib/identity";
import { IdentityContext, IdentitySessionContext } from "./identityContext";
import { toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";

export function IdentityProvider({ children }: { children: React.ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let controller: AbortController | undefined;
    let alive = true;
    let redirecting = false;
    function expired() {
      if (!alive || redirecting) return;
      redirecting = true;
      controller?.abort();
      setIdentity(null);
      const next = window.location.pathname + window.location.search;
      window.location.replace(`/signin?next=${encodeURIComponent(next)}`);
    }
    async function check() {
      controller?.abort();
      const current = new AbortController();
      controller = current;
      try {
        const result = await request<Identity>("auth/me", { signal: current.signal });
        if (!alive || current.signal.aborted) return;
        setFailure(null);
        setIdentity((previous) =>
          previous && identityKey(previous) === identityKey(result) ? previous : result,
        );
      } catch (failure) {
        if (!alive || current.signal.aborted) return;
        if (failure instanceof ApiError && failure.status === 401) expired();
        else {
          setIdentity(null);
          setFailure(toFailure(failure));
        }
      }
    }
    function changed() {
      setIdentity(null);
      void check();
    }
    void check();
    const channel =
      typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("auth-session") : null;
    if (channel) channel.onmessage = changed;
    window.addEventListener("auth:session-ended", expired);
    window.addEventListener("auth:permissions-changed", changed);
    return () => {
      alive = false;
      controller?.abort();
      channel?.close();
      window.removeEventListener("auth:session-ended", expired);
      window.removeEventListener("auth:permissions-changed", changed);
    };
  }, [revision]);

  return (
    <IdentitySessionContext.Provider
      value={{
        identity,
        error: failure?.message ?? "",
        failure,
        reload: () => {
          setFailure(null);
          setRevision((value) => value + 1);
        },
      }}
    >
      <IdentityContext.Provider key={identity ? identityKey(identity) : "pending"} value={identity}>
        {children}
      </IdentityContext.Provider>
    </IdentitySessionContext.Provider>
  );
}
