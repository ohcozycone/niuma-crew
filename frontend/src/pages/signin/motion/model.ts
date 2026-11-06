/** Analytic SVG motion for the approved brand artwork. */
type Glyph = (typeof glyphs)[number];
type Point = {
  x: number;
  y: number;
};
type CrewGlyph = {
  id: string;
  w: number;
  d: string;
  x?: number;
};
const T = {
  prep: 1.12,
  launch: 1.4,
  hit: 2.05,
  rebound: 2.14,
  return: 2.84,
  settle: 3.5,
  wink: 3.86,
};
const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v)),
  mix = (a: number, b: number, u: number) => a + (b - a) * u;
const smooth = (u: number) => {
  u = clamp(u);
  return u * u * (3 - 2 * u);
};
const ease = (u: number) => 1 - Math.pow(1 - clamp(u), 3);
const bump = (t: number, c: number, w: number) => {
  const u = (t - c) / w;
  return Math.abs(u) < 1 ? Math.cos((u * Math.PI) / 2) ** 2 : 0;
};
function key(t: number, entries: number[][]) {
  if (t <= entries[0][0]) return entries[0][1];
  for (let i = 1; i < entries.length; i++) {
    if (t <= entries[i][0]) {
      const u = smooth((t - entries[i - 1][0]) / (entries[i][0] - entries[i - 1][0]));
      return mix(entries[i - 1][1], entries[i][1], u);
    }
  }
  return entries.at(-1)![1];
}
function bez(u: number, a: Point, b: Point, c: Point, d: Point) {
  return {
    x: (1 - u) ** 3 * a.x + 3 * (1 - u) ** 2 * u * b.x + 3 * (1 - u) * u * u * c.x + u ** 3 * d.x,
    y: (1 - u) ** 3 * a.y + 3 * (1 - u) ** 2 * u * b.y + 3 * (1 - u) * u * u * c.y + u ** 3 * d.y,
  };
}
const glyphs = [
  {
    id: "N",
    x: 300,
    w: 92,
    h: 110,
    start: 0.12,
    land: 0.54,
    jump: 0,
    spin: 0,
    bounce: 0,
    d: "M6 0Q0 0 0 -6V-104Q0 -110 6 -110H24Q29 -110 32 -104L65 -49V-104Q65 -110 71 -110H86Q92 -110 92 -104V-6Q92 0 86 0H69Q64 0 61 -5L27 -61V-6Q27 0 21 0Z",
  },
  {
    id: "i",
    x: 407,
    w: 26,
    h: 83,
    start: 0.16,
    land: 0.58,
    jump: 0,
    spin: 0,
    bounce: 0,
    d: "M6 -83H20Q26 -83 26 -77V-6Q26 0 20 0H6Q0 0 0 -6V-77Q0 -83 6 -83Z",
  },
  {
    id: "u",
    x: 443,
    w: 80,
    h: 83,
    start: 0.2,
    land: 0.62,
    jump: 0,
    spin: 0,
    bounce: 0,
    d: "M5 -83H21Q26 -83 26 -78V-36Q26 -22 39 -22Q54 -22 54 -39V-78Q54 -83 59 -83H75Q80 -83 80 -78V-5Q80 0 75 0H59Q54 0 54 -5V-12Q44 3 27 3Q0 3 0 -30V-78Q0 -83 5 -83Z",
  },
  {
    id: "m",
    x: 533,
    w: 130,
    h: 83,
    start: 0.24,
    land: 0.66,
    jump: 0,
    spin: 0,
    bounce: 0,
    d: "M5 0Q0 0 0 -5V-78Q0 -83 5 -83H20Q25 -83 25 -78V-71Q36 -86 50 -86Q68 -86 77 -71Q88 -86 104 -86Q130 -86 130 -56V-5Q130 0 125 0H109Q104 0 104 -5V-52Q104 -64 92 -64Q78 -64 78 -49V-5Q78 0 73 0H57Q52 0 52 -5V-52Q52 -64 40 -64Q26 -64 26 -49V-5Q26 0 21 0Z",
  },
  {
    id: "a",
    x: 675,
    w: 82,
    h: 83,
    start: 0.28,
    land: 0.7,
    jump: 0,
    spin: 0,
    bounce: 0,
    d: "M60 -83H75Q80 -83 80 -78V-5Q80 0 75 0H60Q55 0 55 -5V-12Q45 3 28 3Q-2 3 -2 -40Q-2 -86 28 -86Q45 -86 55 -72V-78Q55 -83 60 -83ZM54 -42Q54 -65 39 -65Q23 -65 23 -42Q23 -19 39 -19Q54 -19 54 -42Z",
  },
];
// Companion caps sit in the lowercase shoulder, sharing N's cap line.
const crew: CrewGlyph[] = [
  {
    id: "C",
    w: 15,
    d: "M14.8 -16.4L13.4 -13.4Q11.5 -14.8 9 -14.8Q3.5 -14.8 3.5 -9Q3.5 -3.2 9 -3.2Q11.5 -3.2 13.5 -4.7L15 -1.8Q12.5 .2 8.8 .2Q0 .2 0 -9Q0 -18.2 8.8 -18.2Q12.4 -18.2 14.8 -16.4Z",
  },
  {
    id: "R",
    w: 16,
    d: "M0 0V-18H7.8Q14.8 -18 14.8 -12Q14.8 -7.7 10.9 -6.4L16 0H11.8L7.2 -5.9H3.4V0ZM3.4 -14.8V-9H7.6Q11.3 -9 11.3 -12Q11.3 -14.8 7.6 -14.8Z",
  },
  {
    id: "E",
    w: 13,
    d: "M1.3 -18H13V-14.8H3.4V-10.7H11.7V-7.6H3.4V-3.2H13V0H1.3Q0 0 0 -1.3V-16.7Q0 -18 1.3 -18Z",
  },
  {
    id: "W",
    w: 23,
    d: "M0 -18H3.6L7 -4.5L10 -16.5Q10.4 -18 11.5 -18Q12.6 -18 13 -16.5L16 -4.5L19.4 -18H23L18.2 -1Q17.9 0 16.8 0H15.4Q14.2 0 13.9 -1.2L11.5 -10.8L9.1 -1.2Q8.8 0 7.6 0H6.2Q5.1 0 4.8 -1Z",
  },
];
let cx = 676;
for (const g of crew) {
  g.x = cx;
  cx += g.w + 4;
}
const packedX = [300, 407, 440, 525, 662];
function tokens(d: string) {
  return d.match(/[MLQCHVZ]|-?(?:\d*\.)?\d+/g)!;
}
function warp(d: string, w: number, h: number, bend = 0) {
  const a = tokens(d);
  const result = [];
  let i = 0;
  const counts: Record<string, number> = { M: 2, L: 2, Q: 4, C: 6, H: 1, V: 1, Z: 0 };
  let px = 0;
  let py = 0;
  while (i < a.length) {
    const cmd = a[i++],
      n = counts[cmd];
    const vals = a.slice(i, i + n).map(Number);
    i += n;
    if (cmd === "Z") {
      result.push("Z");
      continue;
    }
    let points = [];
    if (cmd === "H") {
      points = [vals[0], py];
      px = vals[0];
    } else if (cmd === "V") {
      points = [px, vals[0]];
      py = vals[0];
    } else {
      points = vals;
      px = vals.at(-2)!;
      py = vals.at(-1)!;
    }
    const out = [];
    for (let j = 0; j < points.length; j += 2) {
      const x = points[j] - w / 2,
        y = points[j + 1],
        s = clamp(-y / h, -0.05, 1.5);
      out.push(x + bend * s * s, y + bend * 0.12 * (x / w) * Math.sin(Math.PI * s));
    }
    result.push((cmd === "H" || cmd === "V" ? "L" : cmd) + out.map((v) => v.toFixed(2)).join(" "));
  }
  return result.join(" ");
}
const smoother = (u: number) => {
  u = clamp(u);
  return u * u * u * (u * (u * 6 - 15) + 10);
};
function pressure(p: number) {
  if (p < 0) return 0;
  if (p < 0.16) return ease(p / 0.16);
  if (p < 0.21) return 1;
  return 1 - smoother((p - 0.21) / 0.19);
}
// One driven spring chain. Neighbour displacement and velocity carry the impulse;
// no letter has its own scheduled jump or horizontal tween.
const chainDt = 1 / 480,
  chainMass = [1, 1.55, 0.82],
  chainFrames: {
    x: number[];
    v: number[];
    drive: number;
  }[] = [];
{
  let x = [0, 0, 0];
  let v = [0, 0, 0];
  for (let n = 0; n <= 720; n++) {
    const p = n * chainDt,
      drive = -30 * pressure(p) + (p > 0.21 ? 12 * Math.exp(-Math.pow((p - 0.4) / 0.075, 2)) : 0);
    chainFrames.push({ x: [...x], v: [...v], drive });
    const acc = x.map(
      (q, j) =>
        (420 * ((j ? x[j - 1] : drive) - q) +
          90 * ((j < 2 ? x[j + 1] : q) - q) -
          55 * q -
          14 * v[j]) /
        chainMass[j],
    );
    v = v.map((q, j) => q + acc[j] * chainDt);
    x = x.map((q, j) => q + v[j] * chainDt);
  }
}
function positiveArea(a: number, b: number, dt: number) {
  if (a <= 0 && b <= 0) return 0;
  if (a >= 0 && b >= 0) return ((a + b) * dt) / 2;
  if (a < 0) return (((b * b) / (b - a)) * dt) / 2;
  return (((a * a) / (a - b)) * dt) / 2;
}
const chainEvents = [0, 1, 2].map((j) => {
  const first = chainFrames.findIndex((f, n) => n > 96 && f.x[j] > 0);
  const last = chainFrames.findIndex((f, n) => n > first && f.x[j] <= 0);
  let area = 0;
  const areas = [0];
  for (let n = 1; n < chainFrames.length; n++) {
    if (n >= first && n <= last)
      area += positiveArea(chainFrames[n - 1].x[j], chainFrames[n].x[j], chainDt);
    areas.push(area);
  }
  const lift =
    (first -
      1 -
      chainFrames[first - 1].x[j] / (chainFrames[first].x[j] - chainFrames[first - 1].x[j])) *
    chainDt;
  const land =
    (last -
      1 +
      chainFrames[last - 1].x[j] / (chainFrames[last - 1].x[j] - chainFrames[last].x[j])) *
    chainDt;
  return { lift, land, areas, total: area };
});
function chainState(p: number, j: number) {
  const event = chainEvents[j],
    n = clamp(p / chainDt, 0, chainFrames.length - 1),
    i = Math.floor(n),
    u = n - i;
  const a = chainFrames[i],
    b = chainFrames[Math.min(i + 1, chainFrames.length - 1)],
    x = mix(a.x[j], b.x[j], u),
    left = mix(j ? a.x[j - 1] : a.drive, j ? b.x[j - 1] : b.drive, u);
  const compression = clamp(-x / 25),
    land = p - event.land,
    absorb =
      land >= 0 && land < 0.18
        ? key(land, [
            [0, 0],
            [0.035, 1],
            [0.085, 0.6],
            [0.18, 0],
          ])
        : 0;
  return {
    height: p < event.land ? Math.max(0, x) * 0.9 : 0,
    load: p < event.land ? compression : absorb * 0.7,
    sx: p < event.land ? 1 + 0.025 * compression - 0.025 * clamp(x / 10) : 1 + 0.035 * absorb,
    sy: p < event.land ? 1 - 0.23 * compression + 0.045 * clamp(x / 10) : 1 - 0.18 * absorb,
    bend: p < event.land ? clamp((x - left) / 10, -1, 1) * 2.4 : 0,
    angle: p < event.land ? clamp((x - left) / 15, -1, 1) * 1.5 : 0,
    travel:
      p <= event.lift
        ? 0
        : p >= event.land
          ? 1
          : (event.areas[i] + positiveArea(a.x[j], x, chainDt * u)) / event.total,
  };
}
function letterState(g: Glyph, index: number, t: number) {
  const target = packedX[index] + g.w / 2;
  const s = { x: target, y: 244, sx: 1, sy: 1, angle: 0, bend: 0, opacity: 1 };
  if (t < g.start) return { ...s, y: 218, opacity: 0 };
  if (t < g.land) {
    const u = clamp((t - g.start) / (g.land - g.start));
    s.y = 244 - 26 * (1 - u) ** 2;
    s.sx = 0.985;
    s.sy = 1.025;
    s.opacity = smooth(u / 0.5);
    s.bend = (index % 2 ? 1 : -1) * 1.3 * Math.sin(Math.PI * u);
  } else if (t < g.land + 0.24) {
    const p = t - g.land;
    s.sx = key(p, [
      [0, 0.985],
      [0.065, 1.025],
      [0.24, 1],
    ]);
    s.sy = key(p, [
      [0, 1.025],
      [0.065, 0.915],
      [0.24, 1],
    ]);
  }
  if (g.id === "i" && t >= T.prep && t < T.launch) {
    const u = (t - T.prep) / (T.launch - T.prep),
      load = Math.sin(Math.PI * u) ** 2;
    s.sx += 0.055 * load;
    s.sy -= 0.055 * load;
    s.bend -= 2.5 * load;
  }
  const p = t - T.return;
  if (index === 1 && p >= 0) {
    const load = pressure(p);
    s.sx = 1 + 0.23 * load;
    s.sy = 1 - 0.34 * load;
    s.bend = 0.9 * load;
  }
  if (index >= 2 && p >= 0) {
    const c = chainState(p, index - 2);
    s.x = target + (g.x - packedX[index]) * c.travel;
    s.y -= c.height;
    s.sx = c.sx;
    s.sy = c.sy;
    s.angle = c.angle;
    s.bend = c.bend;
  }
  return s;
}
// Login-only elastic entry: one staggered hop, then a single landing compression.
function loginLetterRaw(g: Glyph, index: number, t: number) {
  if (t >= T.prep) return letterState(g, index, t);
  const s = letterState(g, index, 1.1),
    start = 0.04 + index * 0.055,
    land = 0.54 + index * 0.055;
  if (t < start) {
    s.y += 145;
    return s;
  }
  if (t < land) {
    const u = (t - start) / (land - start),
      v = Math.sin(Math.PI * u);
    s.y += 145 * (1 - u) - 4 * [125, 130, 135, 138, 132][index] * u * (1 - u);
    s.sx = 1 - 0.035 * v;
    s.sy = 1 + 0.075 * v;
    s.angle = (index % 2 ? 1 : -1) * 1.4 * v;
    s.bend = (index % 2 ? 1 : -1) * 1.5 * v;
  } else {
    const p = t - land;
    if (p < 0.1) {
      s.sx = key(p, [
        [0, 1],
        [0.035, 1.03],
        [0.06, 1.025],
        [0.1, 0.985],
      ]);
      s.sy = key(p, [
        [0, 1],
        [0.035, 0.82],
        [0.06, 0.84],
        [0.1, 1.025],
      ]);
      s.y += 2.5 * bump(p, 0.035, 0.065);
    } else if (p < 0.24) {
      const u = (p - 0.1) / 0.14;
      s.y -= 4 * [3, 4, 5, 4, 3][index] * u * (1 - u);
      s.sx = 0.985 + 0.015 * u;
      s.sy = 1.025 - 0.025 * u;
    } else if (p < 0.33) {
      const u = (p - 0.24) / 0.09,
        v = Math.sin(Math.PI * u);
      s.sx = 1 + 0.015 * v;
      s.sy = 1 - 0.06 * v;
      s.y += 0.8 * v;
    }
  }
  return s;
}
function loginHorseRaw(t: number) {
  if (t >= T.prep) return horseState(t);
  const s = horseState(1.1);
  const start = 0.04,
    land = 0.58;
  if (t < start) {
    s.y += 155;
    return s;
  }
  if (t < land) {
    const u = (t - start) / (land - start),
      v = Math.sin(Math.PI * u);
    s.y += 155 * (1 - u) - 4 * 128 * u * (1 - u);
    s.sx = 1 - 0.02 * v;
    s.sy = 1 + 0.035 * v;
    s.angle = -2.2 * v;
  } else if (t < land + 0.25) {
    const u = (t - land) / 0.25,
      v = Math.sin(Math.PI * u);
    s.sy = 1 - 0.09 * v;
    s.sx = 1 + 0.02 * v;
    s.y += 1.8 * v;
  }
  return s;
}
function impactPulse(t: number, c: number) {
  return key(t, [
    [0, 0],
    [c, 0],
    [c + 0.035, 1],
    [c + 0.1, 0.3],
    [c + 0.19, -0.1],
    [c + 0.27, 0],
  ]);
}
function contactLoads(t: number) {
  const p = t - T.return,
    items = [{ x: 239, w: 95, force: 3.4 * impactPulse(t, 0.58) }];
  glyphs.forEach((g, i) => {
    let force = 3.6 * impactPulse(t, 0.54 + i * 0.055);
    let x = packedX[i] + g.w / 2;
    if (i === 1) force += 4.8 * pressure(p);
    if (i >= 2 && p >= 0) {
      const c = chainState(p, i - 2);
      x += (g.x - packedX[i]) * c.travel;
      force += 3.8 * c.load;
    }
    items.push({ x, w: g.w, force });
  });
  return items;
}
function beamAt(t: number, x: number) {
  return (
    contactLoads(t).reduce((sum, v) => sum + v.force * Math.exp(-Math.pow((x - v.x) / 48, 2)), 0) *
    smooth((x - 174) / 34) *
    smooth((766 - x) / 34)
  );
}
function loginLetterState(g: Glyph, i: number, t: number) {
  const s = loginLetterRaw(g, i, t);
  if (s.y >= 244) s.y += beamAt(t, s.x);
  return s;
}
function loginHorseState(t: number) {
  const s = loginHorseRaw(t);
  if (s.y >= 110) s.y += beamAt(t, 239);
  return s;
}
function surfaceFrame(t: number) {
  const h = loginHorseState(t);
  return contactLoads(t).map((v, i) => ({
    ...v,
    height: i ? 244 - loginLetterState(glyphs[i - 1], i - 1, t).y : 110 - h.y,
  }));
}
function flight(u: number, a: Point, b: Point, va: Point, vb: Point, duration: number) {
  return bez(
    clamp(u),
    a,
    { x: a.x + (va.x * duration) / 3, y: a.y + (va.y * duration) / 3 },
    { x: b.x - (vb.x * duration) / 3, y: b.y - (vb.y * duration) / 3 },
    b,
  );
}
function dot(t: number) {
  const stem = letterState(glyphs[1], 1, t);
  let x = stem.x + stem.bend;
  let y = stem.y - 108 * stem.sy;
  let sx = 1;
  let sy = 1;
  const alpha = stem.opacity;
  if (t >= T.launch && t < T.hit) {
    const p = flight(
      (t - T.launch) / (T.hit - T.launch),
      { x: 420, y: 136 },
      { x: 235, y: 116 },
      { x: -240, y: -360 },
      { x: -240, y: 320 },
      T.hit - T.launch,
    );
    x = p.x;
    y = p.y;
  }
  if (t >= T.hit && t < T.rebound) {
    const u = (t - T.hit) / (T.rebound - T.hit),
      load = Math.sin(Math.PI * u) ** 2;
    sx = 1 + 0.26 * load;
    sy = 1 - 0.23 * load;
    const p = headContact(t);
    x = p.x;
    y = p.y - 12 * sy;
  }
  if (t >= T.rebound && t < T.return) {
    const c = headContact(T.rebound);
    const p = flight(
      (t - T.rebound) / (T.return - T.rebound),
      { x: c.x, y: c.y - 12 },
      { x: 420, y: 149 },
      { x: 250, y: -300 },
      { x: 135, y: 430 },
      T.return - T.rebound,
    );
    x = p.x;
    y = p.y;
  }
  if (t >= T.return) {
    const p = t - T.return,
      load = pressure(p);
    sx = 1 + 0.18 * load;
    sy = 1 - 0.18 * load;
    x = stem.x + stem.bend;
    const gap = 13 * smoother((p - 0.22) / 0.4);
    y = stem.y - 83 * stem.sy - 12 * sy - gap;
  }
  // Stretch follows speed continuously and vanishes at both contact points.
  if (t >= T.launch && t < T.hit) {
    const v = Math.sin((Math.PI * (t - T.launch)) / (T.hit - T.launch));
    sx *= 1 - 0.035 * v;
    sy *= 1 + 0.05 * v;
  }
  if (t >= T.rebound && t < T.return) {
    const v = Math.sin((Math.PI * (t - T.rebound)) / (T.return - T.rebound));
    sx *= 1 - 0.035 * v;
    sy *= 1 + 0.05 * v;
  }
  return { x, y, sx, sy, alpha };
}
function blink(t: number, start: number, dur: number) {
  if (t < start || t > start + dur) return 0;
  const u = (t - start) / dur;
  return u < 0.38 ? smooth(u / 0.38) : u < 0.52 ? 1 : 1 - smooth((u - 0.52) / 0.48);
}
function horseState(t: number) {
  let x = 185;
  let y = 110;
  let angle = 0;
  let sx = 1;
  let sy = 1;
  const op = smooth((t - 0.1) / 0.4);
  x += 8 * (1 - ease((t - 0.1) / 0.5));
  const hit = key(t, [
    [0, 0],
    [T.hit, 0],
    [T.hit + 0.055, 1],
    [T.hit + 0.2, 0],
  ]);
  sx += 0.025 * hit;
  sy -= 0.028 * hit;
  y += 2.7 * hit;
  angle -= 1.4 * hit;
  angle += key(t, [
    [0, 0],
    [T.launch, 0],
    [T.hit - 0.12, -0.7],
    [T.hit, 0],
    [T.rebound + 0.12, 1],
    [T.return + 0.2, 0],
  ]);
  return { x, y, angle, sx, sy, op };
}
function headContact(t: number) {
  const h = horseState(t),
    r = (h.angle * Math.PI) / 180;
  const x = (50 - 54) * h.sx,
    y = (18 - 132) * h.sy;
  return {
    x: h.x + 54 + x * Math.cos(r) - y * Math.sin(r),
    y: h.y + 132 + x * Math.sin(r) + y * Math.cos(r),
  };
}
function eyeState(t: number, side: string) {
  const gaze = smooth((t - (T.launch - 0.12)) / 0.18) * (1 - smooth((t - (T.return + 0.1)) / 0.45));
  const h = horseState(t),
    r = (-h.angle * Math.PI) / 180,
    ex = side === "left" ? 35 : 69,
    ey = side === "left" ? 67 : 63;
  let vx = 0;
  let vy = 0;
  let total = 0;
  // A short weighted history follows the arc smoothly without snapping at its apex.
  for (let j = 0; j < 7; j++) {
    const p = dot(Math.max(0, t - 0.035 - j * 0.018)),
      dx = p.x - h.x - 54,
      dy = p.y - h.y - 132,
      w = Math.exp(-j * 0.38);
    const lx = (dx * Math.cos(r) - dy * Math.sin(r)) / h.sx + 54 - ex,
      ly = (dx * Math.sin(r) + dy * Math.cos(r)) / h.sy + 132 - ey,
      len = Math.max(1, Math.hypot(lx, ly));
    vx += (lx / len) * w;
    vy += (ly / len) * w;
    total += w;
  }
  let close = blink(t, T.hit - 0.02 + (side === "left" ? 0.012 : 0), 0.18);
  if (side === "left") close = Math.max(close, blink(t, T.wink, 0.24));
  return {
    px: (vx / total) * (side === "left" ? 3.4 : 2.8) * gaze,
    py: (vy / total) * 3.1 * gaze,
    close,
    alert: gaze * (1 - close),
  };
}
function earState(t: number, side: string, idle = false) {
  const tt = idle ? t - 1.8 : t - T.hit - 0.055 - (side === "left" ? 0.045 : 0);
  if (tt < 0 || tt > 0.72) return 0;
  return (
    (side === "left" ? -1 : 1) *
    (idle ? 8 : 12) *
    Math.sin((tt / 0.72) * Math.PI * 2) *
    Math.exp(-tt * 5)
  );
}
function pathLid(side: string, close: number, alert: number) {
  if (side === "left") {
    const y = 61 - alert * 2.7 + close * 16;
    return `M20 60C19 45 30 43 40 46C48 48 51 56 50 ${y.toFixed(2)}Q35 ${(y - 4 + close * 9).toFixed(2)} 20 ${y.toFixed(2)}Z`;
  }
  const y = 59 - alert * 1.8 + close * 14;
  return `M57 58C57 45 69 43 76 48C81 51 82 55 81 ${y.toFixed(2)}Q68 ${(y - 3 + close * 8).toFixed(2)} 57 ${y.toFixed(2)}Z`;
}
const fmt = (v: number | string) =>
  typeof v === "number" ? v.toFixed(3).replace(/\.?0+$/, "") || "0" : v;
/** @param {SVGSVGElement} svg */
function create(svg: SVGSVGElement) {
  const get = (id: string) => svg.querySelector('[id$="' + id + '"]')!,
    attr = (n: Element, k: string, v: number | string) => n.setAttribute(k, String(v)),
    translate = (n: Element, x: number, y: number) =>
      attr(n, "transform", "translate(" + x + " " + y + ")"),
    scale = (n: Element, x: number, y: number) =>
      attr(n, "transform", "scale(" + x + " " + y + ")");
  const letters = glyphs.map((g) => {
    const root = get("letter-" + g.id);
    return {
      root,
      rotate: root.firstElementChild!,
      scale: root.firstElementChild!.firstElementChild!,
      path: get("contour-" + g.id),
    };
  });
  const caps = crew.map((g) => get("crew-" + g.id)),
    horse = get("horse"),
    rotate = horse.firstElementChild!.firstElementChild!,
    stretch = rotate.firstElementChild!,
    art = stretch.firstElementChild!,
    ears = [art.children[0], art.children[1]];
  const eyes = ["left", "right"].map((side) => {
      const pupil = get(side + "-pupil"),
        shift = pupil.parentElement!,
        group = shift.parentElement!;
      return { side, shift, lid: group.children[2], lash: group.children[3] };
    }),
    mouth = get("mouth"),
    ball = get("i-dot");
  const trail = document.createElementNS("http://www.w3.org/2000/svg", "path");
  for (const [k, v] of Object.entries({
    fill: "none",
    stroke: "var(--logo-ink, #202126)",
    "stroke-width": "1.8",
    "stroke-linecap": "round",
    opacity: "0",
  }))
    attr(trail, k, v);
  ball.parentElement!.before(trail);
  function dotFrame(t: number) {
    if (t < T.prep) {
      const s = loginLetterState(glyphs[1], 1, t);
      return { x: s.x + s.bend, y: s.y - 108 * s.sy, sx: 1, sy: 1, alpha: 1 };
    }
    const d = dot(t);
    if (t >= T.return) d.y += beamAt(t, 420);
    return d;
  }
  function paintEyes(t: number, idle: boolean) {
    for (const e of eyes) {
      const s = idle
        ? { px: 0, py: 0, alert: 0, close: blink(t, 2.1 + (e.side === "left" ? 0.025 : 0), 0.28) }
        : eyeState(t, e.side);
      translate(e.shift, s.px, s.py);
      attr(e.lid, "d", pathLid(e.side, s.close, s.alert));
      attr(e.lash, "opacity", s.close);
    }
  }
  function render(t: number) {
    glyphs.forEach((g, i) => {
      const s = loginLetterState(g, i, t),
        n = letters[i];
      translate(n.root, s.x, s.y);
      attr(n.rotate, "transform", "rotate(" + s.angle + ")");
      scale(n.scale, s.sx, s.sy);
      attr(n.scale, "opacity", s.opacity);
      attr(n.path, "d", warp(g.d, g.w, g.h, s.bend));
    });
    const a = loginLetterState(glyphs[4], 4, t);
    crew.forEach((g, i) =>
      translate(
        caps[i],
        g.x! +
          a.x -
          (glyphs[4].x + glyphs[4].w / 2) +
          a.bend +
          86 * Math.sin((a.angle * Math.PI) / 180) +
          g.w / 2,
        152 + a.y - 244 + 86 * (1 - a.sy),
      ),
    );
    const h = loginHorseState(t);
    translate(horse, h.x, h.y);
    attr(horse, "opacity", h.op);
    attr(rotate, "transform", "rotate(" + h.angle + ")");
    scale(stretch, h.sx, h.sy);
    ears.forEach((n, i) =>
      attr(
        n,
        "transform",
        "rotate(" + earState(t, i ? "right" : "left") + " " + (i ? "76 40" : "36 43") + ")",
      ),
    );
    paintEyes(t, false);
    const smile = smooth((t - T.return - 0.5) / 0.3);
    attr(mouth, "d", "M46 121Q55 " + fmt(117 + smile * 5) + " 64 " + fmt(120 - smile * 2));
    const d = dotFrame(t);
    translate(ball, d.x, d.y);
    attr(ball, "opacity", d.alpha);
    scale(ball.firstElementChild!, d.sx, d.sy);
    const p = dotFrame(t - 0.04),
      q = dotFrame(t - 0.02),
      r = dotFrame(t - 0.008),
      speed =
        Math.hypot(
          dotFrame(t + 0.005).x - dotFrame(t - 0.005).x,
          dotFrame(t + 0.005).y - dotFrame(t - 0.005).y,
        ) / 0.01,
      gate =
        (t > T.launch + 0.08 && t < T.hit - 0.08) || (t > T.rebound + 0.08 && t < T.return - 0.08);
    attr(
      trail,
      "d",
      "M" +
        fmt(p.x) +
        " " +
        fmt(p.y) +
        "Q" +
        fmt(q.x) +
        " " +
        fmt(q.y) +
        " " +
        fmt(r.x) +
        " " +
        fmt(r.y),
    );
    attr(trail, "opacity", gate ? clamp((speed - 230) / 500) * 0.45 : 0);
  }
  return { dispose: () => trail.remove(), render, blink: (t: number) => paintEyes(t, true) };
}
export { create, surfaceFrame };
