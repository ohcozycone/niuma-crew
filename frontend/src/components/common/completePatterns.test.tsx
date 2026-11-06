// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { PageTabs } from "./PageTabs";
import { TabsContent } from "@/components/ui/Tabs";
import { FormField } from "./FormField";
import { SelectField } from "@/components/ui/SelectField";
import { Textarea } from "@/components/ui/Textarea";
import { Input } from "@/components/ui/Input";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";
afterEach(cleanup);
it("connects a complete page tab to its panel, keeps counts named, and leaves trailing status outside keyboard tabs", () => {
  render(
    <PageTabs
      label="页面切换"
      defaultValue="a"
      items={[
        { value: "a", label: "资料", count: 4 },
        { value: "b", label: "设置" },
      ]}
      trailing={<span>更新完成</span>}
    >
      <TabsContent value="a">文档正文</TabsContent>
      <TabsContent value="b">配置正文</TabsContent>
    </PageTabs>,
  );
  const list = screen.getByRole("tablist", { name: "页面切换" });
  expect(screen.getByRole("tab", { name: "资料 4" }).getAttribute("aria-selected")).toBe("true");
  expect(list.contains(screen.getByText("更新完成"))).toBe(false);
  fireEvent.click(screen.getByRole("tab", { name: "设置" }));
  expect(screen.getByRole("tabpanel").textContent).toBe("配置正文");
});
it("standard fields preserve label association and native form values", () => {
  render(
    <form aria-label="表单">
      <FormField label="连接名称">
        <Input name="name" defaultValue="研发" />
      </FormField>
    </form>,
  );
  expect((screen.getByLabelText("连接名称") as HTMLInputElement).value).toBe("研发");
  expect(new FormData(screen.getByRole<HTMLFormElement>("form")).get("name")).toBe("研发");
});
it("long centered dialogs own scrolling without the calling page supplying it", () => {
  render(
    <Dialog defaultOpen>
      <DialogContent>
        <DialogTitle>长文档</DialogTitle>
        <p>{"长内容".repeat(400)}</p>
      </DialogContent>
    </Dialog>,
  );
  expect(screen.getByRole("dialog").classList.contains("dialog-surface")).toBe(true);
  expect(screen.getByRole("button", { name: "关闭" })).toBeTruthy();
});

it("describes ordinary selects and textareas without adding helper copy to their accessible names", () => {
  render(
    <>
      <FormField label="模型预设" description="选择可用模型">
        <SelectField
          value="a"
          options={[{ value: "a", label: "模型A" }]}
          onValueChange={() => {}}
        />
      </FormField>
      <FormField label="工作说明" error="请填写正文">
        <Textarea />
      </FormField>
    </>,
  );
  expect(
    screen.getByRole("combobox", { name: "模型预设" }).getAttribute("aria-describedby"),
  ).toBeTruthy();
  expect(screen.getByRole("textbox", { name: "工作说明" }).getAttribute("aria-invalid")).toBe(
    "true",
  );
});

it("preserves explicit field IDs and descriptions as validation errors appear and clear", () => {
  function Example({ error }: { error?: string }) {
    return (
      <>
        <p id="external-help">已有说明</p>
        <FormField label="服务地址" description="填写完整地址" error={error}>
          <div>
            <Input id="service-url" name="url" aria-describedby="external-help" />
          </div>
        </FormField>
      </>
    );
  }
  const { rerender } = render(<Example error="请检查地址" />);
  const control = screen.getByRole("textbox", { name: "服务地址" });
  expect(control.id).toBe("service-url");
  expect(control.getAttribute("aria-invalid")).toBe("true");
  const descriptions = () =>
    control
      .getAttribute("aria-describedby")
      ?.split(/\s+/)
      .map((id) => document.getElementById(id)?.textContent);
  expect(descriptions()).toEqual(
    expect.arrayContaining(["已有说明", "填写完整地址", "请检查地址"]),
  );
  expect(screen.getByRole("alert").textContent).toBe("请检查地址");
  const label = screen.getByText("服务地址", { selector: "label" }) as HTMLLabelElement;
  expect(label.control).toBe(control);
  rerender(<Example />);
  expect(control.getAttribute("aria-invalid")).not.toBe("true");
  expect(descriptions()).toEqual(expect.arrayContaining(["已有说明", "填写完整地址"]));
  expect(descriptions()).not.toContain("请检查地址");
  expect(screen.queryByRole("alert")).toBeNull();
});
