import type { ToolDescriptor } from "@/lib/api/tools";
import type { DemoAssignment, DemoConnection } from "./fixtures/capabilities";

export function catalogDifferences(previous: ToolDescriptor[], next: ToolDescriptor[]) {
  return [
    ...next.map((tool) => {
      const old = previous.find((item) => item.name === tool.name);
      return {
        tool,
        status: !old
          ? ("added" as const)
          : old.descriptor_hash !== tool.descriptor_hash
            ? ("changed" as const)
            : ("unchanged" as const),
      };
    }),
    ...previous
      .filter((tool) => !next.some((item) => item.name === tool.name))
      .map((tool) => ({ tool, status: "removed" as const })),
  ];
}
export function toolDisplayName(connection: DemoConnection, toolName: string) {
  const alias = connection.aliases[toolName]?.name.trim();
  return alias && alias !== toolName ? `${alias}（${toolName}）` : toolName;
}
export function validGrantedTools(
  assignment: DemoAssignment,
  connection: DemoConnection | undefined,
) {
  if (!assignment.enabled || !connection?.enabled) return [];
  return assignment.tools.filter((name) =>
    connection.approved_catalog.some(
      (tool) => tool.name === name && assignment.toolHashes[name] === tool.descriptor_hash,
    ),
  );
}
export function evaluateDemoCall(
  assignment: DemoAssignment | undefined,
  connection: DemoConnection | undefined,
  name: string,
) {
  if (!assignment?.enabled || !connection?.enabled || !connection.has_credential)
    return { ok: false, message: "当前员工没有可用的账号连接。" };
  if (!assignment.tools.includes(name)) return { ok: false, message: "当前员工没有开启这个操作。" };
  const approved = connection.approved_catalog.find((tool) => tool.name === name);
  if (!approved || assignment.toolHashes[name] !== approved.descriptor_hash)
    return { ok: false, message: "员工的旧许可已失效，请按已确认目录重新授权。" };
  const remote = connection.remoteCatalog.find((tool) => tool.name === name);
  if (!remote || remote.descriptor_hash !== approved.descriptor_hash)
    return {
      ok: false,
      message: "远端目标工具已删除、改名或改变定义。调用已停止，请回能力库检查更新。",
    };
  return {
    ok: true,
    message: "模拟调用通过：员工许可、已确认定义和远端目标工具一致，结果返回 Agent。",
  };
}
