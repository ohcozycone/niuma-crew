// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { createRef, useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Card } from "@/components/ui/Card";
import { SelectField } from "@/components/ui/SelectField";
import { SearchInput } from "@/components/common/SearchInput";

afterEach(cleanup);
it("preserves native form semantics and refs when a panel owns form submission", () => {
  const ref = createRef<HTMLFormElement>();
  const saved = vi.fn();
  render(
    <Card
      as="form"
      variant="outline"
      ref={ref}
      aria-label="配置表单"
      onSubmit={(event) => {
        event.preventDefault();
        saved(new FormData(event.currentTarget).get("name"));
      }}
    >
      <input name="name" defaultValue="连接一" />
      <button type="submit">保存</button>
    </Card>,
  );
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  expect(saved).toHaveBeenCalledWith("连接一");
  expect(ref.current).toBe(screen.getByRole("form", { name: "配置表单" }));
});
it("clears searches inside a form without submitting it and forwards input keyboard handlers", () => {
  const submit = vi.fn(),
    key = vi.fn();
  function SearchForm() {
    const [value, setValue] = useState("模型");
    return (
      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <SearchInput label="搜索名称" value={value} onChange={setValue} onKeyDown={key} />
      </form>
    );
  }
  render(<SearchForm />);
  fireEvent.keyDown(screen.getByRole("textbox", { name: "搜索名称" }), { key: "ArrowDown" });
  expect(key).toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "清空搜索名称" }));
  expect((screen.getByRole("textbox", { name: "搜索名称" }) as HTMLInputElement).value).toBe("");
  expect(submit).not.toHaveBeenCalled();
});
it("renders configured options through the shared popup and keeps disabled states and form values", async () => {
  function Example() {
    const [value, setValue] = useState("personal");
    return (
      <form aria-label="账号表单">
        <label>
          使用范围
          <SelectField
            name="scope"
            value={value}
            onValueChange={setValue}
            options={[
              { value: "personal", label: "个人账号" },
              { value: "shared", label: "共用账号" },
              { value: "blocked", label: "不可用账号", disabled: true },
              { value: "其他", label: "其他" },
            ]}
          />
        </label>
      </form>
    );
  }
  render(<Example />);
  const trigger = screen.getByRole("combobox", { name: "使用范围" });
  expect(trigger.textContent).toContain("个人账号");
  expect(
    new FormData(screen.getByRole("form", { name: "账号表单" }) as HTMLFormElement).get("scope"),
  ).toBe("personal");
  fireEvent.click(trigger);
  const shared = await screen.findByRole("option", { name: "共用账号" });
  expect(screen.getByRole("option", { name: "不可用账号" }).getAttribute("aria-disabled")).toBe(
    "true",
  );
  fireEvent.pointerDown(shared, { pointerType: "mouse" });
  fireEvent.click(shared, { detail: 1 });
  await waitFor(() => expect(trigger.textContent).toContain("共用账号"));
  expect(
    new FormData(screen.getByRole("form", { name: "账号表单" }) as HTMLFormElement).get("scope"),
  ).toBe("shared");
});
