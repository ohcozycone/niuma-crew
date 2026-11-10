import { FailureNotice } from "@/components/failure/FailureNotice";
import type { Failure } from "@/lib/failures/types";
type Props = {
  question: string;
  answer?: string;
  loading: boolean;
  error: string | null;
  failure?: Failure | null;
};

/** 只渲染短文本；读取、版本与生命周期由业务层管理。 */
export function ConversationQuestionPreview({ question, answer, loading, error, failure }: Props) {
  return (
    <div className="animate-[question-preview-in_180ms_ease-out] text-left motion-reduce:animate-none">
      <p className="line-clamp-2 text-sm leading-6 font-semibold break-words">{question}</p>
      {error ? (
        <FailureNotice
          compact
          failure={failure}
          error={error}
          description="预览暂时无法读取，点击刻度可查看完整对话。"
          context={{ operation: "initial-read", resource: "conversation" }}
        />
      ) : (
        <p className="mt-2 line-clamp-3 min-h-12 text-[13px] leading-6 break-words text-text-muted">
          {loading ? "正在读取回答…" : error || answer || "点击刻度查看完整对话。"}
        </p>
      )}
    </div>
  );
}
