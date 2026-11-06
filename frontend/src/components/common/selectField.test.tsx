// @vitest-environment jsdom
import { createRef, useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FormField } from "@/components/common/FormField";
import { SelectField } from "@/components/ui/SelectField";

afterEach(cleanup);

it("keeps labels, descriptions, errors, required state and trigger refs with a decorative icon", () => {
  const ref = createRef<HTMLButtonElement>();
  render(
    <form aria-label="设置">
      <FormField label="选择岗位" description="按工作职责选择" error="请核对岗位">
        <SelectField
          ref={ref}
          name="category"
          required
          value="research"
          onValueChange={vi.fn()}
          icon={<svg aria-label="装饰图标" />}
          displayValue="研究岗位"
          options={[{ value: "research", label: "研究岗位 · 核对资料与来源" }]}
        />
      </FormField>
    </form>,
  );
  const trigger = screen.getByRole("combobox", { name: "选择岗位" });
  expect(ref.current).toBe(trigger);
  expect(trigger.getAttribute("aria-required")).toBe("true");
  expect(trigger.getAttribute("aria-invalid")).toBe("true");
  expect(trigger.textContent).toBe("研究岗位");
  expect(trigger.querySelector("svg")?.closest("[aria-hidden=true]")).toBeTruthy();
  const described = trigger
    .getAttribute("aria-describedby")!
    .split(" ")
    .map((id) => document.getElementById(id)?.textContent);
  expect(described).toEqual(expect.arrayContaining(["按工作职责选择", "请核对岗位"]));
  expect(new FormData(screen.getByRole<HTMLFormElement>("form")).get("category")).toBe("research");
});

it("keeps a valid empty-string choice and applies changed option labels and disabled state", async () => {
  const changed = vi.fn();
  const options = [
    { value: "", label: "暂不绑定" },
    { value: "account", label: "个人账号" },
  ];
  const view = render(
    <SelectField aria-label="账号" value="" options={options} onValueChange={changed} />,
  );
  const trigger = screen.getByRole("combobox", { name: "账号" });
  expect(trigger.textContent).toContain("暂不绑定");
  view.rerender(
    <SelectField
      aria-label="账号"
      value="account"
      options={[options[0], { value: "account", label: "账号已停用", disabled: true }]}
      onValueChange={changed}
    />,
  );
  expect(trigger.textContent).toContain("账号已停用");
  fireEvent.click(trigger);
  const option = await screen.findByRole("option", { name: "账号已停用" });
  expect(option.getAttribute("aria-disabled")).toBe("true");
  fireEvent.click(option);
  expect(changed).not.toHaveBeenCalled();
});

it("opens with the keyboard, rejects disabled choices and selects without submitting the form", async () => {
  const submitted = vi.fn();
  function Example() {
    const [value, setValue] = useState("a");
    return (
      <form aria-label="键盘设置" onSubmit={submitted}>
        <SelectField
          aria-label="模式"
          name="mode"
          value={value}
          onValueChange={setValue}
          options={[
            { value: "a", label: "模式 A" },
            { value: "blocked", label: "不可用", disabled: true },
            { value: "b", label: "模式 B" },
          ]}
        />
      </form>
    );
  }
  render(<Example />);
  const trigger = screen.getByRole("combobox", { name: "模式" });
  act(() => trigger.focus());
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  await screen.findByRole("listbox");
  const first = screen.getByRole("option", { name: "模式 A" });
  await waitFor(() => expect(document.activeElement).toBe(first));
  fireEvent.keyDown(first, { key: "ArrowDown" });
  const disabled = screen.getByRole("option", { name: "不可用" });
  await waitFor(() => expect(document.activeElement).toBe(disabled));
  fireEvent.keyDown(disabled, { key: "Enter" });
  fireEvent.keyUp(disabled, { key: "Enter" });
  expect(trigger.textContent).toContain("模式 A");
  fireEvent.keyDown(disabled, { key: "ArrowDown" });
  const last = screen.getByRole("option", { name: "模式 B" });
  await waitFor(() => expect(document.activeElement).toBe(last));
  fireEvent.keyDown(last, { key: "Enter" });
  fireEvent.keyUp(last, { key: "Enter" });
  await waitFor(() => expect(trigger.textContent).toContain("模式 B"));
  expect(new FormData(screen.getByRole<HTMLFormElement>("form")).get("mode")).toBe("b");
  expect(submitted).not.toHaveBeenCalled();
});

it("does not open or change while the complete field is disabled", () => {
  const changed = vi.fn();
  render(
    <SelectField
      aria-label="禁用选择"
      value="a"
      disabled
      onValueChange={changed}
      options={[{ value: "a", label: "A" }]}
    />,
  );
  fireEvent.click(screen.getByRole("combobox"));
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(changed).not.toHaveBeenCalled();
});
