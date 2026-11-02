import { toFailure, clientFailure } from "@/lib/failures/resolve";
import type { Failure } from "@/lib/failures/types";
import * as api from "@/lib/api/agents";
import { ApiError, request } from "@/lib/api/http";
import type { Agent, AgentSummary } from "@/lib/models/agent";
import { Atom, batchChanges } from "@/state/shared/atom";
import { Resource, ResourceCache, queryKey } from "@/state/shared/resource";

export type AgentPage = { ids: string[]; total: number; publicAgents: api.PublicAgent[] };
export type AgentState = {
  agent?: AgentSummary;
  saving: boolean;
  checking: boolean;
  retryable: boolean;
  error: string;
  failure: Failure | null;
};
type Operation = { field: "is_favorite" | "is_active"; value: boolean; checking: boolean };
export const favoriteQuery = () =>
  new URLSearchParams({ offset: "0", limit: "20", q: "", is_favorite: "true" });

function summaryOf(agent: Agent): AgentSummary {
  return {
    id: agent.id,
    createdByUserId: agent.createdByUserId,
    code: agent.code,
    name: agent.name,
    avatarId: agent.avatarId,
    category: agent.category,
    description: agent.description,
    role: agent.role,
    active: agent.active,
    favorite: agent.favorite,
    revision: agent.revision,
    modelConnectionId: agent.modelConnectionId,
    icon: agent.icon,
    skills:
      agent.skillAssignments?.filter((item) => item.enabled).map((item) => item.skillId) ??
      agent.skills,
    toolCount: agent.toolCount,
    knowledgeBaseCount: agent.knowledgeBaseCount,
  };
}

/** 员工摘要与轻量操作只有一个所有者；页面和侧栏共享 ID、记录、提交锁。 */
export class AgentStore {
  private records = new Map<string, AgentSummary>();
  private states = new Map<string, Atom<AgentState>>();
  private operations = new Map<string, Operation>();
  private reconciling = new Set<string>();
  private checkControllers = new Map<string, AbortController>();
  private errors = new Map<string, Failure>();
  private locks = new Set<string>();
  private pages = new ResourceCache(24);
  private queries = new Map<Resource<AgentPage>, URLSearchParams>();
  private disposed = false;
  private activeWrites = 0;
  constructor(
    readonly admin: boolean,
    private changed: (structural: boolean) => void,
  ) {}
  state(id: string) {
    let state = this.states.get(id);
    if (!state) {
      state = new Atom<AgentState>({
        agent: this.records.get(id),
        saving: false,
        checking: false,
        retryable: false,
        error: "",
        failure: null,
      });
      this.states.set(id, state);
    }
    return state;
  }
  private publish(id: string) {
    const confirmed = this.records.get(id);
    const operation = this.operations.get(id);
    const agent =
      confirmed && operation?.field === "is_favorite" && !operation.checking
        ? { ...confirmed, favorite: operation.value }
        : confirmed;
    this.state(id).set({
      agent,
      saving: this.locks.has(id),
      checking: this.reconciling.has(id),
      retryable: Boolean(operation?.checking && !this.reconciling.has(id)),
      error: this.errors.get(id)?.message ?? "",
      failure: this.errors.get(id) ?? null,
    });
  }
  private merge(agent: AgentSummary) {
    const current = this.records.get(agent.id);
    if (current && (current.revision ?? 0) > (agent.revision ?? 0)) return;
    if (current && JSON.stringify(current) === JSON.stringify(agent)) return;
    this.records.set(agent.id, agent);
    this.publish(agent.id);
  }
  page(query: URLSearchParams): Resource<AgentPage> {
    const key = queryKey(query);
    const resource = this.pages.get<AgentPage>(
      `agents:${key}`,
      async (signal) => {
        if (this.admin) {
          const page = await api.agentPage(new URLSearchParams(key), signal);
          // Resource 只对仍有效的请求调用 accept，不能在这个 await 后提前合并员工。
          return Object.assign(
            { ids: page.items.map((item) => item.id), total: page.total, publicAgents: [] },
            { incoming: page.items.map(api.fromAgentSummary) },
          );
        }
        const page = await request<{ items: api.PublicAgent[]; total: number }>(
          `public/agents?${key}`,
          { signal },
        );
        return {
          ids: page.items.map((item) => item.id),
          total: page.total,
          publicAgents: page.items,
        };
      },
      ["agents"],
      {
        blocked: () => this.activeWrites > 0,
        accept: (page) => {
          const incoming = (page as AgentPage & { incoming?: AgentSummary[] }).incoming ?? [];
          batchChanges(() => incoming.forEach((agent) => this.merge(agent)));
          const retained = new Set(page.ids);
          for (const previous of this.queries.keys())
            if (!previous.isDisposed)
              previous.getSnapshot().data?.ids.forEach((id) => retained.add(id));
          for (const id of this.records.keys())
            if (!retained.has(id) && !this.locks.has(id) && !this.states.get(id)?.observed) {
              this.records.delete(id);
              this.states.delete(id);
            }
          return { ids: page.ids, total: page.total, publicAgents: page.publicAgents };
        },
      },
    );
    for (const previous of this.queries.keys())
      if (previous.isDisposed) this.queries.delete(previous);
    this.queries.set(resource, new URLSearchParams(key));
    return resource;
  }
  statistics(ids: readonly string[]) {
    let snapshot = { available: 0, categories: [] as string[] };
    return {
      subscribe: (listener: () => void) => {
        const unsubscribes = ids.map((id) => this.state(id).subscribe(listener));
        return () => unsubscribes.forEach((unsubscribe) => unsubscribe());
      },
      getSnapshot: () => {
        const agents = ids.flatMap((id) => this.records.get(id) ?? []);
        const available = agents.filter((agent) => agent.active && agent.modelConnectionId).length;
        const categories = [...new Set(agents.map((agent) => agent.category))];
        if (
          available !== snapshot.available ||
          categories.join("\0") !== snapshot.categories.join("\0")
        )
          snapshot = { available, categories };
        return snapshot;
      },
    };
  }
  links(ids: readonly string[]) {
    let snapshot: { id: string; name: string; avatarId: string }[] = [];
    return {
      subscribe: (listener: () => void) => {
        const stops = ids.map((id) => this.state(id).subscribe(listener));
        return () => stops.forEach((stop) => stop());
      },
      getSnapshot: () => {
        const next = ids.flatMap((id) => {
          const agent = this.records.get(id);
          return agent ? [{ id, name: agent.name, avatarId: agent.avatarId }] : [];
        });
        if (
          snapshot.length !== next.length ||
          next.some(
            (item, i) =>
              item.id !== snapshot[i].id ||
              item.name !== snapshot[i].name ||
              item.avatarId !== snapshot[i].avatarId,
          )
        )
          snapshot = next;
        return snapshot;
      },
    };
  }
  private begin(id: string, operation?: Operation) {
    if (this.disposed) throw new Error("当前工作台已关闭，请重新打开页面。");
    if (this.locks.has(id)) throw new Error("正在保存，请稍候。");
    this.locks.add(id);
    this.activeWrites += 1;
    if (operation) this.operations.set(id, operation);
    this.errors.delete(id);
    this.publish(id);
    // 只取消正在进行的读取；普通目录已加载时，点收藏不触发整页重新请求。
    this.pages.cancelPending();
  }
  private end(id: string) {
    this.locks.delete(id);
    this.operations.delete(id);
    if (this.disposed) return;
    this.publish(id);
  }
  private release(id: string, keepLocked = false) {
    this.activeWrites -= 1;
    if (!keepLocked) this.end(id);
    this.pages.resume();
  }
  private confirmed(saved: Agent, previous?: AgentSummary, structural = false) {
    if (this.disposed) return;
    batchChanges(() => {
      this.merge(summaryOf(saved));
      for (const [resource, query] of this.queries) {
        const favoriteFilter = query.get("is_favorite");
        const activeFilter = query.get("is_active");
        const favoriteChanged = previous && previous.favorite !== saved.favorite;
        const activeChanged = previous && previous.active !== saved.active;
        const affected =
          structural ||
          (favoriteFilter !== null && favoriteChanged) ||
          (activeFilter !== null && activeChanged);
        if (!affected) continue;
        const removed =
          (favoriteFilter !== null && saved.favorite !== (favoriteFilter === "true")) ||
          (activeFilter !== null && saved.active !== (activeFilter === "true"));
        resource.update((page) => {
          const present = page.ids.includes(saved.id);
          const unfilteredFavorites =
            favoriteFilter === "true" &&
            !query.get("q") &&
            !query.get("category") &&
            !query.get("skill_id") &&
            activeFilter === null;
          const delta =
            favoriteChanged && unfilteredFavorites
              ? saved.favorite
                ? 1
                : -1
              : removed && present
                ? -1
                : 0;
          return {
            ...page,
            ids: removed ? page.ids.filter((id) => id !== saved.id) : page.ids,
            total: Math.max(0, page.total + delta),
          };
        });
        resource.invalidate();
      }
      this.changed(structural);
    });
  }
  setStatus = async (id: string, field: "is_favorite" | "is_active", value: boolean) => {
    const agent = this.records.get(id);
    if (!this.admin || !agent || this.locks.has(id) || this.disposed) return;
    if ((field === "is_favorite" ? agent.favorite : agent.active) === value) return;
    this.begin(id, { field, value, checking: false });
    let keepLocked = false;
    try {
      const saved = await api.patchAgent(id, { [field]: value }, agent.revision!);
      this.confirmed(saved, agent);
    } catch (failure) {
      if (this.disposed) return;
      const uncertain =
        failure instanceof ApiError &&
        (failure.status === 0 || failure.status === 409 || failure.status >= 500);
      if (uncertain) {
        this.operations.set(id, { field, value, checking: true });
        this.errors.set(id, {
          ...(toFailure(failure) ?? clientFailure("mutation_unknown", "")),
          message: "提交结果尚未确认，正在读取最新状态。",
        });
        this.publish(id);
        keepLocked = !(await this.reconcile(id, agent));
        if (keepLocked) return; // 核对失败仍保留该员工的锁，只允许重试读取。
      } else {
        const reason = toFailure(failure);
        if (reason) this.errors.set(id, reason);
      }
    } finally {
      this.release(id, keepLocked);
    }
  };
  setFavorite = (id: string, value: boolean) => this.setStatus(id, "is_favorite", value);
  private async reconcile(id: string, previous: AgentSummary) {
    if (this.reconciling.has(id)) return false;
    this.reconciling.add(id);
    const controller = new AbortController();
    this.checkControllers.set(id, controller);
    this.publish(id);
    try {
      const latest = await api.getAgent(id, controller.signal);
      if (this.disposed) return true;
      const operation = this.operations.get(id);
      const actual = operation?.field === "is_favorite" ? latest.favorite : latest.active;
      if (operation && operation.value !== actual)
        this.errors.set(
          id,
          clientFailure("mutation_not_applied", "未完成这次更新，已读取最新状态，请确认后重试。"),
        );
      else this.errors.delete(id);
      this.confirmed(latest, previous);
      return true;
    } catch (failure) {
      if (!this.disposed) {
        this.errors.set(id, {
          ...(toFailure(failure) ?? clientFailure("mutation_unknown", "")),
          message: "提交结果尚未确认，核对失败，请重新核对。",
        });
        this.publish(id);
      }
      return false;
    } finally {
      this.reconciling.delete(id);
      this.checkControllers.delete(id);
      if (!this.disposed) this.publish(id);
    }
  }
  retryStatus = async (id: string) => {
    const previous = this.records.get(id);
    if (
      !previous ||
      !this.operations.get(id)?.checking ||
      this.reconciling.has(id) ||
      this.disposed
    )
      return;
    this.errors.set(id, {
      ...(this.errors.get(id) ?? clientFailure("mutation_unknown", "")),
      message: "提交结果尚未确认，正在读取最新状态。",
    });
    this.publish(id);
    this.activeWrites += 1;
    this.pages.cancelPending();
    let keepLocked = true;
    try {
      keepLocked = !(await this.reconcile(id, previous));
    } finally {
      this.release(id, keepLocked);
    }
  };
  save = async (agent: Agent, create: boolean) => {
    const key = create ? "new" : agent.id;
    this.begin(key);
    try {
      const saved = await api.saveAgent(agent, create);
      this.confirmed(saved, this.records.get(saved.id), true);
      return saved;
    } finally {
      this.release(key);
    }
  };
  remove = async (id: string) => {
    this.begin(id);
    try {
      await api.deleteAgent(id);
      if (this.disposed) return;
      batchChanges(() => {
        this.records.delete(id);
        this.publish(id);
        this.pages.invalidate("agents");
        this.changed(true);
      });
    } finally {
      this.release(id);
    }
  };
  invalidate = () => {
    this.pages.invalidate("agents");
  };
  dispose() {
    this.disposed = true;
    this.pages.dispose();
    this.checkControllers.forEach((controller) => controller.abort());
    this.checkControllers.clear();
    this.states.forEach((state) => state.clear());
    this.records.clear();
    this.states.clear();
    this.queries.clear();
  }
}
