import { createContext } from "react";
import type { Identity } from "@/lib/identity";
import type { Failure } from "@/lib/failures/types";

export type IdentitySession = {
  identity: Identity | null;
  error: string;
  failure: Failure | null;
  reload: () => void;
};
export const IdentityContext = createContext<Identity | null>(null);
export const IdentitySessionContext = createContext<IdentitySession | null>(null);
