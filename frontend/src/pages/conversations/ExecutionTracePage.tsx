import { Navigate, useParams, useSearchParams } from "react-router";

/** Existing diagnostic bookmarks open the log dialog in its original business host. */
export function ExecutionTracePage() {
  const { id = "", batchId, caseId } = useParams();
  const [search] = useSearchParams();
  const query = new URLSearchParams();
  if (batchId && caseId) {
    query.set("section", "evaluations");
    query.set("assessment", batchId);
    query.set("log_case", caseId);
    return <Navigate replace to={`/agents/${id}/home?${query}`} />;
  }
  query.set("log_conversation", id);
  const response = search.get("response");
  if (response) query.set("log_response", response);
  return <Navigate replace to={`/conversations?${query}`} />;
}
