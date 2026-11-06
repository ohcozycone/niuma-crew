// @vitest-environment jsdom
import { StrictMode, useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SearchInput } from "./SearchInput";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
function advance(ms: number) {
  act(() => vi.advanceTimersByTime(ms));
}
function setup(delay = 300, initial = "") {
  const changed = vi.fn();
  const submitted = vi.fn();
  function Example() {
    const [value, setValue] = useState(initial);
    return (
      <form onSubmit={submitted}>
        <SearchInput
          label="搜索"
          value={value}
          debounceMs={delay}
          onChange={(next) => {
            changed(next);
            setValue(next);
          }}
        />
      </form>
    );
  }
  const view = render(
    <StrictMode>
      <Example />
    </StrictMode>,
  );
  const input = screen.getByRole("textbox", { name: "搜索" }) as HTMLInputElement;
  return { ...view, input, changed, submitted };
}

it("echoes every keystroke immediately and commits only after the final pause", () => {
  const { input, changed } = setup();
  fireEvent.change(input, { target: { value: "c" } });
  advance(200);
  fireEvent.change(input, { target: { value: "ca" } });
  advance(200);
  fireEvent.change(input, { target: { value: "cat" } });
  expect(input.value).toBe("cat");
  advance(299);
  expect(changed).not.toHaveBeenCalled();
  advance(1);
  expect(changed).toHaveBeenCalledExactlyOnceWith("cat");
  advance(1000);
  expect(changed).toHaveBeenCalledTimes(1);
});

it("keeps local filtering immediate when debounce is disabled", () => {
  const { input, changed } = setup(0);
  fireEvent.change(input, { target: { value: "模型" } });
  expect(changed).toHaveBeenCalledExactlyOnceWith("模型");
  expect(input.value).toBe("模型");
});

it("pauses pending searches throughout IME composition, then waits for the confirmed text", () => {
  const { input, changed } = setup();
  fireEvent.change(input, { target: { value: "z" } });
  advance(100);
  fireEvent.compositionStart(input);
  fireEvent.change(input, { target: { value: "zhong" } });
  fireEvent.keyDown(input, { key: "Enter", isComposing: true });
  advance(1000);
  expect(changed).not.toHaveBeenCalled();
  fireEvent.compositionEnd(input, { target: { value: "中文" } });
  fireEvent.change(input, { target: { value: "中文" } });
  advance(299);
  expect(changed).not.toHaveBeenCalled();
  advance(1);
  expect(changed).toHaveBeenCalledExactlyOnceWith("中文");
});

it("flushes Enter without submitting its surrounding configuration form or repeating the query", () => {
  const { input, changed, submitted } = setup();
  fireEvent.change(input, { target: { value: "财务" } });
  expect(fireEvent.keyDown(input, { key: "Enter" })).toBe(false);
  expect(changed).toHaveBeenCalledExactlyOnceWith("财务");
  advance(1000);
  expect(changed).toHaveBeenCalledTimes(1);
  expect(submitted).not.toHaveBeenCalled();
});

it("does not flush the Enter used to confirm an IME candidate", () => {
  const { input, changed } = setup();
  fireEvent.change(input, { target: { value: "中文" } });
  fireEvent.keyDown(input, { key: "Enter", isComposing: true });
  fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
  expect(changed).not.toHaveBeenCalled();
  advance(300);
  expect(changed).toHaveBeenCalledExactlyOnceWith("中文");
});

it.each(["button", "keyboard"])(
  "clears immediately using %s and cancels the pending query",
  (method) => {
    const { input, changed } = setup(300, "原查询");
    fireEvent.change(input, { target: { value: "新查询" } });
    if (method === "button") fireEvent.click(screen.getByRole("button", { name: "清空搜索" }));
    else fireEvent.change(input, { target: { value: "" } });
    expect(input.value).toBe("");
    expect(changed).toHaveBeenCalledExactlyOnceWith("");
    advance(1000);
    expect(changed).toHaveBeenCalledTimes(1);
  },
);

it("cancels an uncommitted draft when cleared back to the current empty query", () => {
  const { input, changed } = setup();
  fireEvent.change(input, { target: { value: "临时输入" } });
  fireEvent.click(screen.getByRole("button", { name: "清空搜索" }));
  expect(input.value).toBe("");
  advance(1000);
  expect(changed).not.toHaveBeenCalled();
});

it("uses the latest callback without restarting the timer on unrelated renders", () => {
  const first = vi.fn(),
    latest = vi.fn();
  const view = render(<SearchInput label="搜索" value="" onChange={first} debounceMs={300} />);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "技能" } });
  advance(200);
  view.rerender(<SearchInput label="搜索" value="" onChange={latest} debounceMs={300} />);
  advance(100);
  expect(first).not.toHaveBeenCalled();
  expect(latest).toHaveBeenCalledExactlyOnceWith("技能");
});

it("replaces drafts on external navigation and cancels stale callbacks", () => {
  const changed = vi.fn();
  const view = render(
    <SearchInput label="搜索" value="原查询" onChange={changed} debounceMs={300} />,
  );
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "未提交" } });
  view.rerender(<SearchInput label="搜索" value="外部查询" onChange={changed} debounceMs={300} />);
  expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("外部查询");
  advance(1000);
  expect(changed).not.toHaveBeenCalled();
});

it("cancels pending callbacks when disabled or unmounted", () => {
  const changed = vi.fn();
  const view = render(<SearchInput label="搜索" value="" onChange={changed} debounceMs={300} />);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "禁用前" } });
  view.rerender(<SearchInput label="搜索" value="" onChange={changed} debounceMs={300} disabled />);
  advance(300);
  expect(changed).not.toHaveBeenCalled();
  view.rerender(<SearchInput label="搜索" value="" onChange={changed} debounceMs={300} />);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "关闭前" } });
  view.unmount();
  advance(300);
  expect(changed).not.toHaveBeenCalled();
});
