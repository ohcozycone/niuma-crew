import { Atom, batchChanges } from "./atom";
import { toFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";

export type ResourceSnapshot<T> = {
  data: T | undefined;
  loading: boolean;
  error: string;
  failure: Failure | null;
};
type Options<T> = {
  accept?: (value: T) => T;
  blocked?: () => boolean;
  discardOnMissing?: boolean;
};

/** 一份有界读取结果：按需请求、同条件去重、取消旧请求，刷新保留已确认内容。 */
export class Resource<T> {
  private state = new Atom<ResourceSnapshot<T>>({
    data: undefined,
    loading: true,
    error: "",
    failure: null,
  });
  private controller?: AbortController;
  private running?: Promise<void>;
  private sequence = 0;
  private stale = true;
  private disposed = false;
  private observers = 0;
  get isDisposed() {
    return this.disposed;
  }
  get active() {
    return this.observers > 0;
  }
  getSnapshot = this.state.getSnapshot;
  constructor(
    private load: (signal: AbortSignal) => Promise<T>,
    private options: Options<T> = {},
  ) {}
  subscribe = (listener: () => void) => {
    const unsubscribe = this.state.subscribe(listener);
    if (!this.active && this.getSnapshot().error) this.stale = true;
    this.observers += 1;
    void this.ensure();
    return () => {
      unsubscribe();
      this.observers -= 1;
      // StrictMode 会立即重新订阅；同一提交内移交读取方也不必重复发请求。
      queueMicrotask(() => {
        if (!this.active) this.cancelPending();
      });
    };
  };
  ensure = (): Promise<void> => {
    if (this.disposed || !this.stale || !this.active) return Promise.resolve();
    if (this.running) return this.running;
    this.state.set({ ...this.getSnapshot(), loading: true, error: "", failure: null });
    if (this.options.blocked?.()) return Promise.resolve();
    const controller = new AbortController();
    const sequence = ++this.sequence;
    this.controller = controller;
    this.running = Promise.resolve()
      .then(() => {
        if (controller.signal.aborted) throw new Error("读取已取消");
        return this.load(controller.signal);
      })
      .then((value) => {
        if (this.disposed || controller.signal.aborted || sequence !== this.sequence) return;
        batchChanges(() => {
          const data = this.options.accept ? this.options.accept(value) : value;
          this.stale = false;
          this.state.set({ data, loading: false, error: "", failure: null });
        });
      })
      .catch((failure: unknown) => {
        if (this.disposed || controller.signal.aborted || sequence !== this.sequence) return;
        this.stale = false;
        const error = toFailure(failure);
        const discard =
          error?.source === "http" &&
          ([401, 403].includes(error.status ?? 0) ||
            (error.status === 404 && this.options.discardOnMissing));
        this.state.set({
          ...this.getSnapshot(),
          ...(discard ? { data: undefined } : {}),
          loading: false,
          error: error?.message ?? "",
          failure: error,
        });
      })
      .finally(() => {
        if (sequence === this.sequence) {
          this.running = undefined;
          this.controller = undefined;
        }
      });
    return this.running;
  };
  invalidate = () => {
    if (this.disposed) return;
    this.cancelPending();
    this.stale = true;
    if (this.active) {
      this.state.set({ ...this.getSnapshot(), loading: true, error: "", failure: null });
      queueMicrotask(() => {
        void this.ensure();
      });
    }
  };
  refresh = () => {
    this.invalidate();
  };
  cancelPending = () => {
    if (!this.controller) return;
    this.controller.abort();
    this.controller = undefined;
    this.running = undefined;
    this.sequence += 1;
    this.stale = true;
  };
  update(update: (data: T) => T) {
    const current = this.getSnapshot();
    if (current.data !== undefined) {
      const data = update(current.data);
      if (data !== current.data) this.state.set({ ...current, data });
    }
  }
  dispose() {
    this.disposed = true;
    this.cancelPending();
    this.state.clear();
  }
}

/** 只保留有限的最近查询；正在显示的查询不被淘汰。键必须含领域和完整条件。 */
export class ResourceCache {
  private entries = new Map<string, { resource: Resource<unknown>; groups: readonly string[] }>();
  constructor(private limit = 32) {}
  get<T>(
    key: string,
    load: (signal: AbortSignal) => Promise<T>,
    groups: readonly string[] = [],
    options?: Options<T>,
  ): Resource<T> {
    const existing = this.entries.get(key);
    if (existing) {
      this.entries.delete(key);
      this.entries.set(key, existing);
      return existing.resource as Resource<T>;
    }
    const resource = new Resource(load, options);
    this.entries.set(key, { resource: resource as Resource<unknown>, groups });
    for (const [oldKey, entry] of this.entries) {
      if (this.entries.size <= this.limit) break;
      if (oldKey !== key && !entry.resource.active) {
        entry.resource.dispose();
        this.entries.delete(oldKey);
      }
    }
    return resource;
  }
  invalidate(...groups: string[]) {
    for (const entry of this.entries.values())
      if (entry.groups.some((group) => groups.includes(group))) entry.resource.invalidate();
  }
  cancelPending() {
    this.entries.forEach(({ resource }) => resource.cancelPending());
  }
  resume() {
    this.entries.forEach(({ resource }) => {
      void resource.ensure();
    });
  }
  dispose() {
    this.entries.forEach(({ resource }) => resource.dispose());
    this.entries.clear();
  }
}

export function queryKey(query: URLSearchParams) {
  const canonical = new URLSearchParams(query);
  canonical.sort();
  return canonical.toString();
}
