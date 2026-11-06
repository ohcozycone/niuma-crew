import { useLocation, useSearchParams } from "react-router";

export function useQueryState(name: string, fallback = "") {
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const value = params.get(name) ?? fallback;
  function update(next: string | null) {
    setParams(
      (current) => {
        const copy = new URLSearchParams(current);
        if (
          ["q", "filter", "category"].includes(name) ||
          (name === "skill" && location.pathname.startsWith("/agents"))
        )
          copy.delete("offset");
        if (["skill_q", "skill_category"].includes(name)) copy.delete("skill_offset");
        if (next === null || next === fallback || next === "") copy.delete(name);
        else copy.set(name, next);
        return copy;
      },
      { replace: true, preventScrollReset: true },
    );
  }
  return [value, update] as const;
}
