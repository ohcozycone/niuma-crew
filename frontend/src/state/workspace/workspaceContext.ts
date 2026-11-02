import { createContext } from "react";
import type { WorkspaceData } from "./workspaceData";
export const WorkspaceContext = createContext<WorkspaceData | null>(null);
