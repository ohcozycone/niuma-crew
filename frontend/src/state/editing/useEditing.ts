import {
  createContext,
  createElement,
  useContext,
  useLayoutEffect,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from "react";

type Editor = { dirty: boolean; saving: boolean; isSaving: () => boolean; discard: () => void };
class EditingRegistry {
  entries = new Map<symbol, Editor>();
  listeners = new Set<() => void>();
  manualSaving = false;
  snapshot = { dirty: false, saving: false };
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  getSnapshot = () => this.snapshot;
  isDirty = () => [...this.entries.values()].some((entry) => entry.dirty);
  refresh = () => {
    const dirty = this.isDirty();
    const saving = this.isSaving();
    if (dirty !== this.snapshot.dirty || saving !== this.snapshot.saving) {
      this.snapshot = { dirty, saving };
      this.listeners.forEach((listener) => listener());
    }
  };
  register = (key: symbol, editor: Editor) => {
    this.entries.set(key, editor);
    this.refresh();
    return () => {
      this.entries.delete(key);
      this.refresh();
    };
  };
  isSaving = () =>
    this.manualSaving ||
    [...this.entries.values()].some((entry) => entry.saving || entry.isSaving());
  setSaving = (value: boolean) => {
    this.manualSaving = value;
    this.refresh();
  };
  discard = () => {
    if (!this.isSaving()) this.entries.forEach((entry) => entry.discard());
  };
}
const EditingContext = createContext<EditingRegistry | null>(null);
export function EditingProvider({ children }: { children: ReactNode }) {
  const registry = useRef<EditingRegistry | null>(null);
  if (!registry.current) registry.current = new EditingRegistry();
  return createElement(EditingContext.Provider, { value: registry.current }, children);
}
const standalone = new EditingRegistry();
export function useEditing() {
  const registry = useContext(EditingContext) ?? standalone;
  const snapshot = useSyncExternalStore(
    registry.subscribe,
    registry.getSnapshot,
    registry.getSnapshot,
  );
  return {
    ...snapshot,
    isDirty: registry.isDirty,
    isSaving: registry.isSaving,
    setSaving: registry.setSaving,
    discard: registry.discard,
  };
}
/** 编辑器显式说明是否脏、是否正在保存，以及如何放弃自己的草稿。 */
export function useEditingRegistration(editor: Editor) {
  const registry = useContext(EditingContext);
  const current = useRef(editor);
  current.current = editor;
  const key = useRef(Symbol("editor"));
  useLayoutEffect(() => {
    if (!registry) return;
    return registry.register(key.current, {
      get dirty() {
        return current.current.dirty;
      },
      get saving() {
        return current.current.saving;
      },
      isSaving: () => current.current.isSaving(),
      discard: () => current.current.discard(),
    });
  }, [registry]);
  useLayoutEffect(() => {
    registry?.refresh();
  }, [registry, editor.dirty, editor.saving]);
}
