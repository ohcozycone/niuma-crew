import { useEffect, useState, type ReactNode } from "react";
import { useIdentity } from "@/state/auth/useIdentity";
import { identityKey } from "@/lib/identity";
import { WorkspaceData } from "./workspaceData";
import { WorkspaceContext } from "./workspaceContext";

function ScopedDataProvider({ admin, children }: { admin: boolean; children: ReactNode }) {
  const [data] = useState(() => new WorkspaceData(admin));
  useEffect(() => data.retain(), [data]);
  return <WorkspaceContext.Provider value={data}>{children}</WorkspaceContext.Provider>;
}

export function WorkspaceDataProvider({ children }: { children: ReactNode }) {
  const identity = useIdentity();
  return (
    <ScopedDataProvider
      key={identityKey(identity)}
      admin={identity.permissions.includes("agents:read")}
    >
      {children}
    </ScopedDataProvider>
  );
}
