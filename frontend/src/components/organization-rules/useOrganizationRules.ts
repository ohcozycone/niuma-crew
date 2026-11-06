import { toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import { useEffect, useState } from "react";
import { loadOrganizationRules, type OrganizationRules } from "@/lib/api/organizationRules";

export function useOrganizationRules() {
  const [rules, setRules] = useState<OrganizationRules | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    loadOrganizationRules(controller.signal).then(
      (value) => {
        if (!controller.signal.aborted) {
          setRules(value);
          setFailure(null);
        }
      },
      (error: unknown) => {
        if (!controller.signal.aborted) {
          const value = toFailure(error);
          setFailure(value);
          if ([401, 403, 404].includes(value?.status ?? 0)) setRules(null);
        }
      },
    );
    return () => controller.abort();
  }, [attempt]);
  function reload() {
    setFailure(null);
    setAttempt((value) => value + 1);
  }
  return { rules, failure, error: failure?.message ?? "", reload };
}
