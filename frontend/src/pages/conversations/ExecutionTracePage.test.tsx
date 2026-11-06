// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { ExecutionTracePage } from "./ExecutionTracePage";

afterEach(cleanup);
function Host() {
  const location = useLocation();
  return <p>{location.pathname + location.search}</p>;
}
it("opens an old conversation trace bookmark in the history dialog", async () => {
  render(
    <MemoryRouter initialEntries={["/conversations/100000000001/trace?response=100000000002"]}>
      <Routes>
        <Route path="/conversations/:id/trace" element={<ExecutionTracePage />} />
        <Route path="/conversations" element={<Host />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(
    await screen.findByText(
      "/conversations?log_conversation=100000000001&log_response=100000000002",
    ),
  ).toBeTruthy();
});
it("opens an old assessment trace bookmark inside the original report", async () => {
  render(
    <MemoryRouter initialEntries={["/agents/employee/evaluations/batch/cases/case/trace"]}>
      <Routes>
        <Route
          path="/agents/:id/evaluations/:batchId/cases/:caseId/trace"
          element={<ExecutionTracePage />}
        />
        <Route path="/agents/:id/home" element={<Host />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(
    await screen.findByText(
      "/agents/employee/home?section=evaluations&assessment=batch&log_case=case",
    ),
  ).toBeTruthy();
});
