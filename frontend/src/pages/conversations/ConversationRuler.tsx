import { useEffect, useRef, useState, type ReactNode } from "react";
import { maxVisibleQuestions, rulerStart } from "./questionNavigation";

type Props = {
  /** 用于刻度窗口跟随；高亮始终来自 visibleNumbers。 */
  current: number;
  visibleNumbers: readonly number[];
  total: number;
  windowStart?: number;
  onBrowse?: (delta: number, visible: number) => void;
  renderTick?: (number: number, visible: boolean, line: ReactNode) => ReactNode;
};

/** 当前窗口及少量缓冲共用稳定轮次 key，滑动时不重建已有刻度。 */
export function ConversationRuler({
  current,
  visibleNumbers,
  total,
  windowStart,
  onBrowse,
  renderTick,
}: Props) {
  const ruler = useRef<HTMLSpanElement>(null);
  const tickStep = 10;
  const [height, setHeight] = useState(maxVisibleQuestions * tickStep);
  const touch = useRef<{ y: number; dragged: boolean } | null>(null);
  useEffect(() => {
    const node = ruler.current;
    if (!node) return;
    const measure = () => {
      if (node.clientHeight) setHeight(node.clientHeight);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const visible = Math.max(1, Math.floor(height / tickStep));
  const start = Math.max(
    0,
    Math.min(windowStart ?? rulerStart(current, total, visible), total - visible),
  );
  useEffect(() => {
    const node = ruler.current;
    if (!node || !onBrowse) return;
    let remainder = 0;
    const wheel = (event: WheelEvent) => {
      if (!event.deltaY || event.ctrlKey) return;
      // React 的 wheel 监听默认 passive；原生非 passive 监听才能阻止正文滚动。
      event.preventDefault();
      event.stopPropagation();
      const delta =
        event.deltaY * (event.deltaMode === 1 ? tickStep : event.deltaMode === 2 ? height : 1);
      if (Math.sign(delta) !== Math.sign(remainder)) remainder = 0;
      remainder += delta;
      const steps = Math.trunc(remainder / tickStep);
      if (steps) {
        remainder -= steps * tickStep;
        onBrowse(steps, visible);
      }
    };
    node.addEventListener("wheel", wheel, { passive: false });
    return () => node.removeEventListener("wheel", wheel);
  }, [onBrowse, visible, height]);
  const first = Math.max(1, start - 3);
  const end = Math.min(total, start + visible + 4);
  return (
    <span
      ref={ruler}
      aria-hidden={renderTick || onBrowse ? undefined : true}
      data-slot="conversation-ruler"
      data-window-start={start}
      role={onBrowse ? "group" : undefined}
      tabIndex={onBrowse ? 0 : undefined}
      aria-label={onBrowse ? "滚动浏览问题；可使用方向键、翻页键和首尾键" : undefined}
      className="relative block w-7 max-h-[40dvh] touch-none overflow-hidden rounded-small outline-none select-none focus-visible:ring-1 focus-visible:ring-focus focus-within:[mask-image:none] [mask-image:linear-gradient(to_bottom,transparent,black_5px,black_calc(100%_-_5px),transparent)]"
      style={{ height: Math.min(total, maxVisibleQuestions) * tickStep }}
      onKeyDown={(event) => {
        if (!onBrowse) return;
        const delta = {
          ArrowUp: -1,
          ArrowDown: 1,
          PageUp: -visible,
          PageDown: visible,
          Home: -total,
          End: total,
        }[event.key];
        if (delta === undefined) return;
        event.preventDefault();
        event.stopPropagation();
        // 窗口换页可能卸载原按钮，焦点保留在稳定的刻度容器上。
        event.currentTarget.focus({ preventScroll: true });
        onBrowse(delta, visible);
      }}
      onPointerDown={(event) => {
        touch.current = event.pointerType === "touch" ? { y: event.clientY, dragged: false } : null;
      }}
      onPointerMove={(event) => {
        const gesture = touch.current;
        if (!onBrowse || !gesture || event.pointerType !== "touch") return;
        const steps = Math.trunc((gesture.y - event.clientY) / tickStep);
        if (!steps) return;
        gesture.y -= steps * tickStep;
        gesture.dragged = true;
        event.currentTarget.setPointerCapture(event.pointerId);
        onBrowse(steps, visible);
      }}
      onPointerCancel={() => {
        touch.current = null;
      }}
      onClickCapture={(event) => {
        if (touch.current?.dragged) {
          touch.current = null;
          event.preventDefault();
          event.stopPropagation();
        }
      }}
    >
      {Array.from({ length: Math.max(0, end - first + 1) }, (_, i) => first + i).map((number) => {
        const inView = number > start && number <= start + visible;
        const highlighted = visibleNumbers.includes(number);
        const line = (
          <span
            className={`block h-px rounded-full transition-[width,background-color] duration-(--os-motion-normal) ease-out group-hover/ruler-tick:w-4 group-hover/ruler-tick:bg-text group-focus-visible/ruler-tick:w-4 group-focus-visible/ruler-tick:bg-text motion-reduce:transition-none ${highlighted ? "w-4 bg-text" : number % 5 === 0 ? "w-2.5 bg-text-muted/50" : "w-2 bg-text-muted/35"}`}
          />
        );
        return (
          <span
            key={number}
            data-question-number={number}
            data-visible={highlighted || undefined}
            aria-hidden={!inView || undefined}
            className="absolute top-0 right-0 flex h-2.5 w-7 items-center justify-center transition-transform duration-(--os-motion-normal) ease-out motion-reduce:transition-none"
            style={{ transform: `translateY(${(number - start - 1) * tickStep}px)` }}
          >
            {renderTick ? renderTick(number, inView, line) : line}
          </span>
        );
      })}
    </span>
  );
}
