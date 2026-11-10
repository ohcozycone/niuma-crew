import { clearDraft, draftKey, readDraft } from "@/lib/draft";
import type { ConversationInput } from "@/lib/api/conversationTransport";

export const conversationSessionKey = (owner: string, id: string) =>
  draftKey(owner, `conversation:v3:${id}`);

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
