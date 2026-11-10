type Listener = () => void;
let batchDepth = 0;
const scheduled = new Set<Listener>();

/** 先提交本次操作的全部数据，再通知订阅者，避免数量与列表分别显示中间状态。 */
export function batchChanges(action: () => void) {
  batchDepth += 1;
  try {
    action();
  } finally {
    batchDepth -= 1;
    if (!batchDepth) {
      const listeners = [...scheduled];
      scheduled.clear();
      listeners.forEach((listener) => listener());
    }
  }
}

export class Atom<T> {
  private listeners = new Set<Listener>();
  constructor(private value: T) {}
  get observed() {
    return this.listeners.size > 0;
  }
  getSnapshot = () => this.value;
  subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  set(value: T) {
    if (Object.is(value, this.value)) return;
    this.value = value;
    this.listeners.forEach((listener) => {
      if (batchDepth) scheduled.add(listener);
      else listener();
    });
  }
  clear() {
    this.listeners.clear();
  }
}
