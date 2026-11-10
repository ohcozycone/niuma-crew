import type { getQuestions, getQuestionPreview } from "@/lib/api/conversations";

/** 会话接入层的数据契约；展示组件不依赖具体 HTTP 实现。 */
export type QuestionNavigationSource = {
  questions: typeof getQuestions;
  preview: typeof getQuestionPreview;
};

export const maxVisibleQuestions = 13;

export function rulerStart(current: number, total: number, visible: number) {
  return Math.max(0, Math.min(current - Math.ceil(visible / 2), total - visible));
}
