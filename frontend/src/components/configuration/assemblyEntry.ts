import type { ReactNode } from "react";
import type { ResourceKind } from "@/components/common/ResourceIcon";

export type AssemblyEntry = {
  key: string;
  kind: ResourceKind;
  name: string;
  summary: string;
  element: ReactNode;
};

export type AssemblyCandidate = {
  key: string;
  kind: ResourceKind;
  name: string;
  summary: string;
  disabled?: boolean;
  selected?: boolean;
  disabledReason?: string;
  select: () => void;
};
