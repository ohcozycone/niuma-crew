import { create, surfaceFrame } from "./model";
const clamp = (value: number) => Math.max(0, Math.min(1, value));
const smooth = (value: number) => {
  const x = clamp(value);
  return x * x * (3 - 2 * x);
};
export function installSigninMotion(root: HTMLElement) {
  const find = <T extends Element>(selector: string) => {
    const node = root.querySelector<T>(selector);
    if (!node) throw new Error(`Missing signin node: ${selector}`);
    return node;
  };
  const rig = create(find<SVGSVGElement>("[data-signin-perch] svg"));
  const path = find<SVGPathElement>("[data-signin-edge]"),
    surface = find<SVGSVGElement>("[data-signin-surface]"),
    shadows = find<SVGGElement>("[data-signin-shadows]"),
    canvas = find<HTMLElement>("[data-signin-canvas]"),
    stage = find<HTMLElement>("[data-signin-stage]");
  const soles = [
    [[4, 27]],
    [
      [-32, 21],
      [32, 21],
    ],
    [[0, 20]],
    [
      [-12, 23],
      [27, 18],
    ],
    [
      [-52, 19],
      [0, 19],
      [52, 19],
    ],
    [
      [-13, 25],
      [27, 18],
    ],
  ];
  const nodes = soles.map((items) =>
    items.map(() => {
      const node = document.createElementNS("http://www.w3.org/2000/svg", "ellipse");
      node.setAttribute("fill", "var(--login-shadow)");
      shadows.append(node);
      return node;
    }),
  );
  let frame = 0,
    start = 0,
    time = 4.3,
    metrics = { w: 0, h: 0, offset: 0, scale: 1 };
  function measure() {
    const w = canvas.clientWidth,
      bw = stage.offsetWidth,
      scale = bw / 592,
      floor = stage.offsetTop + 141.5 * scale;
    metrics = { w, h: canvas.clientHeight - floor, offset: (w - bw) / 2, scale };
    surface.setAttribute("viewBox", `0 0 ${w} ${metrics.h}`);
  }
  function paint(t: number) {
    time = t;
    rig.render(t);
    const { w, h, offset, scale } = metrics,
      items = surfaceFrame(t),
      edge = Math.min(54, offset + 8);
    const base = (x: number) => 10 * (1 - smooth(x / edge)) + 10 * smooth((x - w + edge) / edge);
    const y = (x: number) =>
      base(x) +
      items.reduce(
        (sum: number, v: { force: number; x: number }) =>
          sum +
          v.force *
            scale *
            Math.exp(-Math.pow((x - offset - (v.x - 174) * scale) / (48 * scale), 2)),
        0,
      ) *
        smooth((x - offset) / (34 * scale)) *
        smooth((offset + 592 * scale - x) / (34 * scale));
    let d = `M0 ${y(0)}`;
    for (let i = 0; i < 56; i++) {
      const a = (w * i) / 56,
        b = (w * (i + 1)) / 56,
        dx = (b - a) / 3,
        s0 = (y(a + 0.1) - y(a - 0.1)) / 0.2,
        s1 = (y(b + 0.1) - y(b - 0.1)) / 0.2;
      d += `C${a + dx} ${y(a) + s0 * dx} ${b - dx} ${y(b) - s1 * dx} ${b} ${y(b)}`;
    }
    path.setAttribute("d", `${d}L${w} ${h}H0Z`);
    items.forEach((v: { x: number; height: number }, i: number) =>
      soles[i].forEach(([dx, width], j) => {
        const x = offset + (v.x + dx - 174) * scale,
          node = nodes[i][j];
        for (const [key, value] of Object.entries({
          cx: x,
          cy: y(x) + 0.7,
          rx: (width * scale) / 2,
          ry: 0.7 * scale,
          opacity: 0.14 * clamp(1 - Math.abs(v.height) / 50),
        }))
          node.setAttribute(key, String(value));
      }),
    );
  }
  function stop() {
    cancelAnimationFrame(frame);
    frame = 0;
  }
  function tick(now: number) {
    frame = 0;
    paint(Math.min(4.6, (now - start) / 1000));
    if (time < 4.6) frame = requestAnimationFrame(tick);
    else root.dataset.motion = "finished";
  }
  const api = {
    play() {
      stop();
      start = performance.now();
      root.dataset.motion = "playing";
      paint(0);
      frame = requestAnimationFrame(tick);
    },
    finish() {
      if (!frame && time === 4.3) return;
      stop();
      paint(4.3);
      root.dataset.motion = "finished";
    },
    resize() {
      measure();
      paint(time);
    },
    dispose() {
      stop();
      rig.dispose();
      nodes.flat().forEach((node) => node.remove());
    },
  };
  measure();
  paint(4.3);
  return api;
}
