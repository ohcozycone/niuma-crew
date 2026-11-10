// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { Button } from "./Button";

afterEach(cleanup);

it("loading blocks repeated actions, exposes busy state and restores the original action", () => {
  const save = vi.fn();
  const { rerender } = render(
    <Button loading onClick={save}>
      保存配置
    </Button>,
  );
  const button = screen.getByRole("button", { name: "保存配置" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  expect(button.getAttribute("aria-busy")).toBe("true");
  fireEvent.click(button);
  expect(save).not.toHaveBeenCalled();
  rerender(<Button onClick={save}>保存配置</Button>);
  expect(button.disabled).toBe(false);
  expect(button.hasAttribute("aria-busy")).toBe(false);
  fireEvent.click(button);
  expect(save).toHaveBeenCalledOnce();
});

it("keeps explicit disabled and caller busy state after loading finishes", () => {
  const { rerender } = render(
    <Button loading disabled aria-busy={false}>
      保存
    </Button>,
  );
  const button = screen.getByRole("button", { name: "保存" }) as HTMLButtonElement;
  expect(button.getAttribute("aria-busy")).toBe("true");
  rerender(
    <Button disabled aria-busy>
      保存
    </Button>,
  );
  expect(button.disabled).toBe(true);
  expect(button.getAttribute("aria-busy")).toBe("true");
});

it("preserves composed link navigation and forwards the button ref", () => {
  const ref = createRef<HTMLButtonElement>();
  render(
    <>
      <Button ref={ref}>操作</Button>
      <Button nativeButton={false} render={<a href="/agents" />}>
        数字员工
      </Button>
    </>,
  );
  expect(ref.current).toBe(screen.getByRole("button", { name: "操作" }));
  const link = screen.getByRole("button", { name: "数字员工" });
  expect(link.tagName).toBe("A");
  expect(link.getAttribute("href")).toBe("/agents");
});

it("blocks a loading composed link as well as its click handler", () => {
  const click = vi.fn();
  render(
    <Button loading nativeButton={false} render={<a href="/agents" />} onClick={click}>
      打开员工
    </Button>,
  );
  const button = screen.getByRole("button", { name: "打开员工" });
  expect(button.getAttribute("aria-disabled")).toBe("true");
  fireEvent.click(button);
  expect(click).not.toHaveBeenCalled();
});
