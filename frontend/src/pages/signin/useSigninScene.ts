import { useCallback, useLayoutEffect, useRef } from "react";
import { signinLayout } from "./geometry";
import { signinLayoutConfig } from "./layoutConfig";

type Motion = { finish: () => void; dispose: () => void; resize: () => void; play: () => void };

export function useSigninScene() {
  const rootRef = useRef<HTMLDivElement>(null);
  const motionRef = useRef<Motion | null>(null);
  const interacted = useRef(false);
  const finish = useCallback(() => {
    interacted.current = true;
    motionRef.current?.finish();
    if (rootRef.current) rootRef.current.dataset.motion = "static";
  }, []);
  useLayoutEffect(() => {
    const root = rootRef.current!;
    let alive = true;
    let frame = 0;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)");
    const resize = () => {
      for (const [key, value] of Object.entries(
        signinLayout(
          document.documentElement.clientWidth,
          window.visualViewport?.height || innerHeight,
          signinLayoutConfig,
        ),
      ))
        root.style.setProperty(`--${key}`, value);
      motionRef.current?.resize();
    };
    const hidden = () => {
      if (document.hidden) finish();
    };
    const reduced = () => {
      if (reduce.matches) finish();
    };
    resize();
    window.addEventListener("resize", resize);
    window.visualViewport?.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", hidden);
    window.addEventListener("pagehide", finish);
    reduce.addEventListener("change", reduced);
    async function loadMotion() {
      const connection = (
        navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }
      ).connection;
      if (
        !alive ||
        interacted.current ||
        reduce.matches ||
        document.hidden ||
        connection?.saveData ||
        ["2g", "slow-2g"].includes(connection?.effectiveType || "")
      )
        return;
      const navigation = performance.getEntriesByType("navigation")[0] as
        PerformanceNavigationTiming | undefined;
      if (
        navigation &&
        (navigation.responseStart - navigation.requestStart > 250 ||
          navigation.responseEnd - navigation.responseStart > 160)
      )
        return;
      const started = performance.now();
      root.dataset.motion = "loading";
      try {
        const { installSigninMotion } = await import("./motion/controller");
        if (
          !alive ||
          interacted.current ||
          reduce.matches ||
          document.hidden ||
          performance.now() - started > 180
        ) {
          if (alive) root.dataset.motion = "static";
          return;
        }
        motionRef.current = installSigninMotion(root);
        motionRef.current.play();
      } catch {
        if (alive) root.dataset.motion = "static";
      }
    }
    performance.mark("signin-brand-ready");
    frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => {
        void loadMotion();
      });
    });
    return () => {
      alive = false;
      cancelAnimationFrame(frame);
      motionRef.current?.dispose();
      motionRef.current = null;
      window.removeEventListener("resize", resize);
      window.visualViewport?.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", hidden);
      window.removeEventListener("pagehide", finish);
      reduce.removeEventListener("change", reduced);
    };
  }, [finish]);
  return { rootRef, finish };
}
