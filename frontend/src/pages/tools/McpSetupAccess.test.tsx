// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { McpSetupAccess } from "./McpSetupAccess";

afterEach(cleanup);
it.each([
  { transport: "http" as const, auth: "bearer", label: "API Key / Token" },
  { transport: "stdio" as const, auth: "env", label: "SERVICE_KEY" },
])(
  "associates $transport credential instructions without changing the field name",
  ({ transport, auth, label }) => {
    const description = "请填写服务方颁发的凭据";
    render(
      <McpSetupAccess
        transport={transport}
        auth={auth}
        fields={[{ name: "SERVICE_KEY", description, is_required: true, is_secret: true }]}
        keys={["SERVICE_KEY"]}
        scope="personal"
        header=""
        token=""
        environment={{}}
        onScope={vi.fn()}
        onAuth={vi.fn()}
        onHeader={vi.fn()}
        onToken={vi.fn()}
        onEnvironment={vi.fn()}
      />,
    );
    const input = screen.getByLabelText(label, { exact: true });
    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)?.textContent).toBe(description);
    expect(input.hasAttribute("required")).toBe(true);
    expect(input.getAttribute("type")).toBe("password");
  },
);
