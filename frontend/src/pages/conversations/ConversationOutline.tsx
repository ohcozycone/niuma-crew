import { FailureNotice } from "@/components/failure/FailureNotice";
import type { Failure } from "@/lib/failures/types";
import { useCallback, useId, useRef, useState } from "react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/Tooltip";
import type { ConversationQuestion } from "@/lib/api/conversations";
import { ConversationRuler } from "./ConversationRuler";
import { ConversationQuestionPreview } from "./ConversationQuestionPreview";
import { useQuestionNavigation } from "./useQuestionNavigation";
import { useQuestionPreview } from "./useQuestionPreview";
import type { QuestionNavigationSource } from "./questionNavigation";

export type QuestionNavigationControl = {
  pending: boolean;
  error: string | null;
  failure?: Failure | null;
  navigate: (questionId: string) => void;
};

type Props = {
  conversationId: string | null;
  latestQuestionId: string | null;
  visibleQuestionIds: readonly string[];
  navigation: QuestionNavigationControl;
  source?: QuestionNavigationSource;
};

/** 将可见问答组接入目录；问题 ID 始终同时作为点击定位目标。 */
export function ConversationOutline(props: Props) {
  return props.conversationId ? (
    <QuestionNavigation
      key={props.conversationId}
      {...props}
      conversationId={props.conversationId}
    />
  ) : null;
}

function QuestionPreview({
  id,
  question,
  read,
}: {
  id: string;
  question: ConversationQuestion;
  read: QuestionNavigationSource["preview"];
}) {
  const preview = useQuestionPreview(id, question.id, read);
  return (
    <ConversationQuestionPreview
      question={preview.data?.question || question.preview}
      answer={preview.data?.answer}
      loading={preview.loading}
      error={preview.error}
      failure={preview.failure}
    />
  );
}

function QuestionNavigation({
  conversationId,
  latestQuestionId,
  visibleQuestionIds,
  navigation,
  source,
}: Props & { conversationId: string }) {
  const currentAnchorId = visibleQuestionIds[0] ?? null;
  const directory = useQuestionNavigation({
    id: conversationId,
    revision: latestQuestionId ?? undefined,
    currentAnchorId,
    source,
  });
  const { total, currentNumber, windowStart, byNumber } = directory;
  const visibleIds = new Set(visibleQuestionIds);
  const visibleNumbers = [...byNumber.values()]
    .filter((question) => visibleIds.has(question.id))
    .map((question) => question.number);
  const [previewOpen, setPreviewOpen] = useState(false);
  const clickedAt = useRef<{ x: number; y: number } | null>(null);
  const previewId = useId();
  const failure = directory.failure;
  const browse = directory.browse;
  const browseQuestions = useCallback(
    (delta: number, visible: number) => {
      clickedAt.current = null;
      setPreviewOpen(false);
      browse(delta, visible);
    },
    [browse],
  );
  const retry = directory.retry;
  if (directory.hidden || directory.pending) return null;
  return (
    <nav
      aria-label="问题导航"
      aria-busy={navigation.pending}
      className="absolute top-1/2 right-2 z-20 -translate-y-1/2"
      onPointerMove={(event) => {
        const point = clickedAt.current;
        if (point && (point.x !== event.clientX || point.y !== event.clientY)) {
          clickedAt.current = null;
        }
      }}
      onPointerLeave={() => {
        clickedAt.current = null;
      }}
    >
      {!total && failure ? (
        <FailureNotice
          compact
          className="max-w-56"
          failure={directory.failureFact}
          error={failure}
          context={{ operation: "initial-read", resource: "conversation" }}
          actions={[{ label: "重试", kind: "retry", onClick: retry }]}
        />
      ) : (
        <TooltipProvider delay={80}>
          <Tooltip<ConversationQuestion>
            open={previewOpen}
            onOpenChange={(open, details) => {
              if (open && details.reason === "trigger-hover" && clickedAt.current) {
                details.cancel();
                return;
              }
              if (open && details.reason === "trigger-focus") clickedAt.current = null;
              setPreviewOpen(open);
            }}
          >
            {({ payload }) => (
              <>
                <ConversationRuler
                  current={currentNumber}
                  visibleNumbers={visibleNumbers}
                  total={total}
                  windowStart={windowStart}
                  onBrowse={browseQuestions}
                  renderTick={(number, visible, line) => {
                    const question = byNumber.get(number);
                    if (!question || !visible) return line;
                    return (
                      <TooltipTrigger
                        payload={question}
                        delay={80}
                        closeDelay={100}
                        aria-label={`跳转到第 ${number} 个问题：${question.preview}`}
                        aria-description={
                          visibleIds.has(question.id) ? "此轮对话当前可见" : undefined
                        }
                        aria-describedby={payload?.id === question.id ? previewId : undefined}
                        className="focus-inset group/ruler-tick flex h-full w-full cursor-pointer items-center justify-center rounded-small outline-none focus-visible:ring-1 focus-visible:ring-focus"
                        onClick={(event) => {
                          // 定位会让刻度滑到静止指针下；等真实移针后再允许预览。
                          clickedAt.current = { x: event.clientX, y: event.clientY };
                          setPreviewOpen(false);
                          directory.follow();
                          navigation.navigate(question.id);
                        }}
                      >
                        {line}
                      </TooltipTrigger>
                    );
                  }}
                />
                <TooltipContent
                  id={previewId}
                  role="tooltip"
                  side="left"
                  sideOffset={10}
                  showArrow={false}
                  positionerClassName="transition-[transform,top,left] duration-(--os-motion-normal) ease-out motion-reduce:transition-none"
                  className="w-80 max-w-[calc(100vw-72px)] rounded-card border border-border bg-surface p-4 text-wrap text-text shadow-popover transition-opacity duration-(--os-motion-normal) data-starting-style:opacity-0 data-ending-style:opacity-0 motion-reduce:transition-none"
                >
                  {payload && (
                    <QuestionPreview
                      key={payload.id}
                      id={conversationId}
                      question={payload}
                      read={directory.source.preview}
                    />
                  )}
                  {navigation.error && (
                    <FailureNotice
                      compact
                      failure={navigation.failure}
                      error={navigation.error}
                      context={{
                        operation: "refresh",
                        resource: "conversation",
                        hasUsableData: true,
                      }}
                    />
                  )}
                </TooltipContent>
              </>
            )}
          </Tooltip>
        </TooltipProvider>
      )}
      {total > 0 && failure && (
        <FailureNotice
          compact
          className="max-w-56"
          failure={directory.failureFact}
          error={failure}
          context={{ operation: "refresh", resource: "conversation", hasUsableData: true }}
          actions={[{ label: "重试问题导航", kind: "retry", onClick: retry }]}
        />
      )}
    </nav>
  );
}
