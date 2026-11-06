import type { signinLayoutConfig } from "./layoutConfig";

/** Pure layout shared by the initial inline sizing and client resize handling. */
export function signinLayout(width: number, height: number, config: typeof signinLayoutConfig) {
  const mobile = width <= config.breakpoint;
  const available = width - 26;
  const w = mobile
    ? Math.min(config.mobileMax, Math.max(config.mobileMin, available))
    : Math.min(config.desktopMax, Math.max(config.desktopMin, available));
  const h = mobile ? config.mobileHeight : config.desktopHeight;
  const scale = Math.min(1, available / w, Math.max(0.82, (height - 34) / h));
  const brandWidth = mobile ? w - 40 : Math.min(config.content, w - 64);
  const floor = (mobile ? 57 : 65) + (141.5 * brandWidth) / 592;
  return {
    w: `${w}px`,
    h: `${h}px`,
    scale: String(scale),
    "box-w": `${w * scale + 2}px`,
    "box-h": `${h * scale + 2}px`,
    floor: `${floor}px`,
    "body-y": `${floor + (mobile ? config.bodyMobile : config.bodyDesktop)}px`,
  };
}
