import { useContext } from "react";
import { WorkspaceContext } from "./workspaceContext";
export function useWorkspaceData() {
  const data = useContext(WorkspaceContext);
  if (!data) throw new Error("共享数据必须在 WorkspaceDataProvider 内使用。");
  return data;
}
