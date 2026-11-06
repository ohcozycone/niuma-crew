import * as api from "@/lib/api/skills";
import { request } from "@/lib/api/http";
import type { Skill, SkillListItem } from "@/lib/models/skill";
import { ResourceCache, queryKey } from "@/state/shared/resource";

type SkillPage = { items: SkillListItem[]; total: number };

export class SkillStore {
  private queries = new ResourceCache(24);
  private locks = new Set<string>();
  private disposed = false;
  constructor(
    private admin: boolean,
    private changed: () => void,
  ) {}
  page(query: URLSearchParams) {
    const key = queryKey(query);
    return this.queries.get<SkillPage>(
      `skills:${key}`,
      async (signal) => {
        if (this.admin) {
          const page = await api.skillPage(new URLSearchParams(key), signal);
          return { items: page.items.map(api.fromSkillSummary), total: page.total };
        }
        const page = await request<{ items: api.PublicSkill[]; total: number }>(
          `public/skills?${key}`,
          { signal },
        );
        return { items: page.items.map(api.fromPublicSkill), total: page.total };
      },
      ["skills"],
    );
  }
  detail(id: string) {
    return this.queries.get<Skill | null>(
      `skill:${id}`,
      async (signal) => {
        if (!id || id === "new") return null;
        return this.admin
          ? api.getSkill(id, signal)
          : api.fromPublicSkill(await request<api.PublicSkill>(`public/skills/${id}`, { signal }));
      },
      ["skills"],
      { discardOnMissing: true },
    );
  }
  private async write<T>(key: string, action: () => Promise<T>) {
    if (this.disposed) throw new Error("当前工作台已关闭，请重新打开页面。");
    if (this.locks.has(key)) throw new Error("正在保存，请稍候。");
    this.locks.add(key);
    try {
      const value = await action();
      if (!this.disposed) this.updated();
      return value;
    } finally {
      this.locks.delete(key);
    }
  }
  save = (skill: Skill, create: boolean) =>
    this.write(create ? "new" : skill.id, () => api.saveSkill(skill, create));
  remove = (id: string) => this.write(id, () => api.deleteSkill(id));
  importPackage = (archive: string, name: string) =>
    this.write("import", () => api.importSkillPackage(archive, name));

  syncDirectory = () => this.write("sync", api.syncSkillLibrary);
  updated = () => {
    if (this.disposed) return;
    this.queries.invalidate("skills");
    this.changed();
  };
  dispose() {
    this.disposed = true;
    this.queries.dispose();
  }
}
