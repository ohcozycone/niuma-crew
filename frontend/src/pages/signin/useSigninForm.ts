import { toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, request } from "@/lib/api/http";
import { notifyIdentityChange, type Identity } from "@/lib/identity";
import { safeReturnPath } from "@/lib/navigation";
import {
  githubSigninFailure,
  requiredCredentials,
  signinFailure,
  type InvalidField,
} from "./formState";

export function useSigninForm(onInteract: () => void) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState<"password" | "guest" | "github" | null>(null);
  const [githubEnabled, setGithubEnabled] = useState(false);
  const [feedback, setFeedback] = useState<{
    message: string;
    fields: InvalidField[];
    failure?: Failure | null;
  }>({
    message: "",
    fields: [],
  });
  const gate = useRef(false);
  const alive = useRef(false);
  const identityProbe = useRef<AbortController | null>(null);
  const submitRef = useRef<HTMLButtonElement>(null);
  const oauthError = new URLSearchParams(location.search).get("auth_error");
  const interact = useCallback(() => {
    identityProbe.current?.abort();
    onInteract();
  }, [onInteract]);

  useEffect(() => {
    alive.current = true;
    const identity = new AbortController();
    const providers = new AbortController();
    identityProbe.current = identity;
    if (oauthError) setFeedback({ message: githubSigninFailure(oauthError), fields: [] });
    void request<{ github: { enabled: boolean } }>("auth/providers", { signal: providers.signal })
      .then((value) => {
        if (!providers.signal.aborted) setGithubEnabled(value.github.enabled);
      })
      .catch(() => {
        /* Provider discovery does not block password or guest entry. */
      });
    void request<Identity>("auth/me", { signal: identity.signal })
      .then((value) => {
        if (!identity.signal.aborted && !gate.current && !oauthError && value.actor.kind === "user")
          location.replace(safeReturnPath(new URLSearchParams(location.search).get("next")));
      })
      .catch((failure: unknown) => {
        if (!identity.signal.aborted && !(failure instanceof ApiError && failure.status === 401))
          setFeedback({ message: signinFailure(failure), fields: [], failure: toFailure(failure) });
      });
    performance.mark("signin-form-ready");
    const restored = (event: PageTransitionEvent) => {
      if (event.persisted) location.reload();
    };
    window.addEventListener("pageshow", restored);
    return () => {
      alive.current = false;
      identity.abort();
      providers.abort();
      window.removeEventListener("pageshow", restored);
    };
  }, [oauthError]);

  function clearFeedback() {
    setFeedback({ message: "", fields: [] });
  }
  async function enter(kind: "password" | "guest" | "github") {
    if (gate.current || (kind === "github" && !githubEnabled)) return;
    interact();
    clearFeedback();
    if (kind === "password") {
      const missing = requiredCredentials(username, password);
      if (missing.fields.length) {
        setFeedback(missing);
        submitRef.current?.focus({ preventScroll: true });
        return;
      }
    }
    gate.current = true;
    setPending(kind);
    try {
      const next = safeReturnPath(new URLSearchParams(location.search).get("next"));
      if (kind === "github") {
        const result = await request<{ authorization_url: string }>("auth/github", {
          method: "POST",
          body: JSON.stringify({ next }),
        });
        if (alive.current) location.assign(result.authorization_url);
        return;
      }
      await request<Identity>(kind === "guest" ? "auth/guest" : "auth/login", {
        method: "POST",
        body: JSON.stringify(kind === "guest" ? {} : { username: username.trim(), password }),
      });
      if (!alive.current) return;
      setPassword("");
      notifyIdentityChange();
      location.replace(kind === "guest" ? "/" : next);
    } catch (failure) {
      if (!alive.current) return;
      if (kind !== "github") setPassword("");
      setFeedback({
        failure: toFailure(failure),
        message:
          kind === "github"
            ? githubSigninFailure(failure instanceof ApiError ? (failure.code ?? "") : "")
            : signinFailure(failure),
        fields:
          kind !== "github" && failure instanceof ApiError && failure.code === "invalid_credentials"
            ? ["username", "password"]
            : [],
      });
      gate.current = false;
      setPending(null);
    }
  }
  return {
    username,
    setUsername,
    password,
    setPassword,
    pending,
    githubEnabled,
    feedback,
    clearFeedback,
    interact,
    enter,
    submitRef,
  };
}
