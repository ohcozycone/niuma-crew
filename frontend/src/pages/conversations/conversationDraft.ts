import { clearDraft, draftKey, readDraft } from "@/lib/draft";
import type { ConversationInput } from "@/lib/api/conversationTransport";

export const conversationSessionKey = (owner: string, id: string) =>
  draftKey(owner, `conversation:${id}`);

/** 同一导航入口只分配一次 ID；StrictMode 重建也不会生成两份会话。 */
export function createLocalConversation(owner: string, agentId: string, entryKey: string) {
  const key = draftKey(owner, `conversation-entry:${entryKey}`);
  try {
    const existing = sessionStorage.getItem(key);
    if (existing) return existing;
  } catch {
    /* 无存储时由挂载生命周期保留 ID。 */
  }
  const id = crypto.randomUUID();
  try {
    sessionStorage.setItem(key, id);
    sessionStorage.setItem(draftKey(owner, `conversation-create:${id}`), agentId);
  } catch {
    /* 新对话仍可在本页发送。 */
  }
  return id;
}

export function localConversationAgent(owner: string, id: string) {
  try {
    return sessionStorage.getItem(draftKey(owner, `conversation-create:${id}`)) ?? undefined;
  } catch {
    return undefined;
  }
}

export function composeInput(
  content: string,
  selectedSkillIds: readonly string[],
): ConversationInput {
  return { content: content.trim(), selectedSkillIds };
}

/** 接受确认只清理匹配的旧稿；等待期间编辑的新内容继续保留。 */
export function clearAcceptedDraft(key: string, accepted: ConversationInput) {
  const content = readDraft(key, { content: "" }).content;
  if (content.trim() === accepted.content) clearDraft(key);
}

/** 清理退役入口的本地稿，避免排查重点在普通输入框中被重新发送。 */
export function retireLegacyConversationDraft(key: string, retiredEntry: boolean): boolean {
  try {
    if (!retiredEntry && sessionStorage.getItem(`${key}:ci`) === null) return false;
    clearDraft(`${key}:ci`);
    clearDraft(key);
    return true;
  } catch {
    return retiredEntry;
  }
}
