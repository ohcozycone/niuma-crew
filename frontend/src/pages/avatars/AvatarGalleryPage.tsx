import { useEffect, useRef, useState } from "react";
import { PageHeading } from "@/components/common/PageHeading";
import { SvgAvatar, svgCharacters, type SvgCharacterId } from "@/components/avatars/svgAvatar";
import styles from "./svgGalleryStyles";

const backgrounds = [
  { id: "warm", label: "暖色", color: "var(--os-selected)" },
  { id: "light", label: "主题表面", color: "var(--os-surface)" },
  { id: "dark", label: "反差", color: "var(--os-text)" },
  { id: "transparent", label: "透明", color: "transparent" },
] as const;
export function AvatarGalleryPage() {
  const [theme, setTheme] = useState<(typeof backgrounds)[number]>(backgrounds[0]);
  const [selected, setSelected] = useState<SvgCharacterId>("designer-bull");
  const [zoom, setZoom] = useState(1);
  const viewport = useRef<HTMLDivElement>(null);
  const label = svgCharacters.find((role) => role.id === selected)!.label;
  useEffect(() => {
    document.title = "SVG 头像 · NiumaCrew";
  }, []);
  useEffect(() => {
    const view = viewport.current;
    if (!view) return;
    const [x, y] = svgCharacters.find((role) => role.id === selected)!.focus;
    const size = 320 * zoom;
    view.scrollLeft = Math.max(0, (x / 1254) * size - view.clientWidth / 2);
    view.scrollTop = Math.max(0, (y / 1254) * size - view.clientHeight / 2);
  }, [selected, zoom]);
  const transparent = theme.id === "transparent";
  return (
    <div className="workspace-region">
      <main className={styles.page}>
        <PageHeading
          title={`${svgCharacters.length} 个角色，一套 SVG 头像。`}
          description="可缩放、可编辑的静态母版，直接用于列表、卡片和个人资料。"
          actions={
            <a className={styles.back} href="/">
              返回项目 ↗
            </a>
          }
        />
        <div className={styles.toolbar} aria-label="头像背景">
          <span>背景</span>
          {backgrounds.map((bg) => (
            <button
              key={bg.id}
              type="button"
              aria-pressed={theme.id === bg.id}
              onClick={() => setTheme(bg)}
            >
              <i style={{ background: bg.color }} />
              {bg.label}
            </button>
          ))}
          <span className={styles.note}>透明背景母版 · 原生矢量</span>
        </div>
        <div className={styles.grid}>
          {svgCharacters.map(({ id, label: name }) => (
            <article className={styles.card} key={id}>
              <button
                type="button"
                className={`${styles.portrait} ${transparent ? styles.checker : ""}`}
                style={{ backgroundColor: theme.color }}
                onClick={() => setSelected(id)}
                aria-label={`查看${name}细节`}
                aria-pressed={selected === id}
              >
                <SvgAvatar character={id} size="100%" alt={name} />
              </button>
              <div className={styles.cardTitle}>
                <h2>{name}</h2>
                <a href={`/avatars/svg/${id}.svg`} download>
                  下载 SVG ↓
                </a>
              </div>
              <p className={styles.identifier}>{id}</p>
              <div className={styles.samples} aria-label={`${name}小尺寸预览`}>
                {[32, 48, 96].map((size) => (
                  <div key={size}>
                    <SvgAvatar character={id} size={size} />
                    <span>{size}px</span>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
        <section className={styles.detail} aria-label="放大检查">
          <div className={styles.detailTitle}>
            <div>
              <p className={styles.eyebrow}>DETAIL VIEW</p>
              <h2>{label} · 细节预览</h2>
            </div>
            <div className={styles.zoom}>
              {[1, 4, 8].map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={zoom === value}
                  onClick={() => setZoom(value)}
                >
                  {value * 100}%
                </button>
              ))}
            </div>
          </div>
          <div
            ref={viewport}
            className={`${styles.viewport} ${transparent ? styles.checker : ""}`}
            style={{ backgroundColor: theme.color }}
          >
            <SvgAvatar character={selected} size={320 * zoom} alt={`${label}放大预览`} />
          </div>
          <p className={styles.hint}>
            点击上方角色切换，放大后可滚动查看轮廓。放大显示的是同一份 SVG。
          </p>
        </section>
        <section className={styles.usage}>
          <div>
            <p className={styles.eyebrow}>IN YOUR PROJECT</p>
            <h2>一行组件，直接使用。</h2>
            <p>支持尺寸、可访问名称和背景颜色；无需动画播放器。</p>
          </div>
          <pre>
            <code>{`import { SvgAvatar } from "@/components/avatars/index";\n\n<SvgAvatar\n  character="${selected}"\n  size={96}\n  alt="${label}"\n/>`}</code>
          </pre>
        </section>
      </main>
    </div>
  );
}
