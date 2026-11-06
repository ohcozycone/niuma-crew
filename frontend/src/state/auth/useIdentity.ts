import { useContext } from "react";
import { IdentityContext, IdentitySessionContext } from "./identityContext";

export function useIdentity() {
  const identity = useContext(IdentityContext);
  if (!identity) throw new Error("Identity must be loaded before accessing the workspace.");
  return identity;
}

export function useIdentitySession() {
  const session = useContext(IdentitySessionContext);
  if (!session) throw new Error("IdentityProvider is missing.");
  return session;
}
