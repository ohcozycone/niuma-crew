// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ConversationRuler } from "./ConversationRuler";
afterEach(cleanup);
it("keeps the ruler bounded for very long conversations and moves shared ticks down when reading earlier", () => {
  const { container, rerender } = render(
    <ConversationRuler visibleNumbers={[9000]} total={10000} current={9000} />,
  );
  expect(container.querySelectorAll("[data-question-number]").length).toBeLessThanOrEqual(21);
  const tick = container.querySelector<HTMLElement>('[data-question-number="9000"]')!;
  const before = tick.style.transform;
  rerender(<ConversationRuler total={10000} current={8999} visibleNumbers={[8999]} />);
  expect(container.querySelector('[data-question-number="9000"]')).toBe(tick);
  expect(before).toBe("translateY(60px)");
  expect(tick.style.transform).toBe("translateY(70px)");
  expect(container.querySelector("[data-visible]")?.getAttribute("data-question-number")).toBe(
    "8999",
  );
});
it("keeps the first and last questions inside the visible window without phantom ticks", () => {
  const { container, rerender } = render(
    <ConversationRuler total={3} current={1} visibleNumbers={[1]} />,
  );
  expect(
    [...container.querySelectorAll("[data-question-number]")].map((e) =>
      e.getAttribute("data-question-number"),
    ),
  ).toEqual(["1", "2", "3"]);
  rerender(<ConversationRuler total={10000} current={10000} visibleNumbers={[10000]} />);
  expect(container.querySelector("[data-visible]")?.getAttribute("data-question-number")).toBe(
    "10000",
  );
  expect(container.querySelector<HTMLElement>("[data-visible]")?.style.transform).toBe(
    "translateY(120px)",
  );
  rerender(<ConversationRuler total={10000} current={1} visibleNumbers={[1]} />);
  expect(container.querySelector<HTMLElement>("[data-visible]")?.style.transform).toBe(
    "translateY(0px)",
  );
});
it("uses the visible range for highlighting and the reading anchor only for window following", () => {
  const { container, rerender } = render(
    <ConversationRuler total={8} current={2} visibleNumbers={[2, 3, 4]} />,
  );
  expect(container.querySelectorAll("[data-visible]")).toHaveLength(3);
  for (const tick of container.querySelectorAll("[data-visible]")) {
    expect(tick.firstElementChild?.className).toContain("w-4 bg-text");
  }
  rerender(<ConversationRuler total={8} current={2} visibleNumbers={[]} />);
  expect(container.querySelector("[data-visible]")).toBeNull();
});
it("accumulates small wheel movements, supports line/page units, and preserves browser zoom", () => {
  const onBrowse = vi.fn();
  render(
    <ConversationRuler visibleNumbers={[9000]} total={10000} current={9000} onBrowse={onBrowse} />,
  );
  const ruler = screen.getByRole("group");
  fireEvent.wheel(ruler, { deltaY: -4 });
  expect(onBrowse).not.toHaveBeenCalled();
  fireEvent.wheel(ruler, { deltaY: -6 });
  expect(onBrowse).toHaveBeenLastCalledWith(-1, 13);
  fireEvent.wheel(ruler, { deltaY: 2, deltaMode: 1 });
  expect(onBrowse).toHaveBeenLastCalledWith(2, 13);
  fireEvent.wheel(ruler, { deltaY: 1, deltaMode: 2 });
  expect(onBrowse).toHaveBeenLastCalledWith(13, 13);
  const zoom = new WheelEvent("wheel", { deltaY: 100, ctrlKey: true, cancelable: true });
  fireEvent(ruler, zoom);
  expect(zoom.defaultPrevented).toBe(false);
  expect(onBrowse).toHaveBeenCalledTimes(3);
});
it("keeps keyboard focus on the stable ruler while paging", () => {
  const onBrowse = vi.fn();
  render(
    <ConversationRuler visibleNumbers={[9000]} total={10000} current={9000} onBrowse={onBrowse} />,
  );
  const ruler = screen.getByRole("group");
  fireEvent.keyDown(ruler, { key: "PageUp" });
  expect(onBrowse).toHaveBeenLastCalledWith(-13, 13);
  expect(document.activeElement).toBe(ruler);
});
it("browses by touch drag without activating a question, while a tap remains clickable", () => {
  const onBrowse = vi.fn(),
    onJump = vi.fn();
  render(
    <ConversationRuler
      visibleNumbers={[50]}
      total={100}
      current={50}
      onBrowse={onBrowse}
      renderTick={(n, visible) => (visible ? <button onClick={onJump}>{n}</button> : null)}
    />,
  );
  const ruler = screen.getByRole("group");
  Object.defineProperty(ruler, "setPointerCapture", { value: vi.fn() });
  const trigger = screen.getAllByRole("button")[0];
  const pointer = (type: string, y: number) => {
    const event = new Event(type, { bubbles: true });
    Object.defineProperties(event, {
      pointerType: { value: "touch" },
      pointerId: { value: 1 },
      clientY: { value: y },
    });
    fireEvent(trigger, event);
  };
  pointer("pointerdown", 100);
  pointer("pointermove", 120);
  pointer("pointerup", 120);
  expect(onBrowse).toHaveBeenCalledWith(-2, 13);
  fireEvent.click(trigger);
  expect(onJump).not.toHaveBeenCalled();
  pointer("pointerdown", 100);
  pointer("pointerup", 100);
  fireEvent.click(trigger);
  expect(onJump).toHaveBeenCalledTimes(1);
});
