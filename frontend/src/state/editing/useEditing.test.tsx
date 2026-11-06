// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { EditingProvider, useEditing, useEditingRegistration } from "./useEditing";
afterEach(cleanup);
it("registers current dirty state, checks the synchronous save gate and cleans up", () => {
  const discard = vi.fn();
  let busy = false;
  const view = renderHook(
    ({ dirty }) => {
      useEditingRegistration({ dirty, saving: false, isSaving: () => busy, discard });
      return useEditing();
    },
    { initialProps: { dirty: true }, wrapper: EditingProvider },
  );
  const previousRender = view.result.current;
  expect(view.result.current.dirty).toBe(true);
  expect(previousRender.isDirty()).toBe(true);
  busy = true;
  expect(view.result.current.isSaving()).toBe(true);
  act(() => view.result.current.discard());
  expect(discard).not.toHaveBeenCalled();
  busy = false;
  act(() => view.result.current.discard());
  expect(discard).toHaveBeenCalledTimes(1);
  view.rerender({ dirty: false });
  expect(view.result.current.dirty).toBe(false);
  expect(previousRender.dirty).toBe(true);
  expect(previousRender.isDirty()).toBe(false);
  const registry = view.result.current;
  view.unmount();
  registry.discard();
  expect(discard).toHaveBeenCalledTimes(1);
});
