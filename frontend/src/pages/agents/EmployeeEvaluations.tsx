import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ClipboardCheck, Plus } from "lucide-react";
import { useQueryState } from "@/hooks/useQueryState";
import { useFailureState } from "@/state/shared/useFailureState";
import { useSaveOperation } from "@/state/editing/useSaveOperation";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeading } from "@/components/common/PageHeading";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ExecutionLogDialog } from "@/components/execution/ExecutionLogDialog";
import {
  activeEvaluation,
  evaluationList,
  evaluationReport,
  evaluationSuites,
  createEvaluation,
  cancelEvaluation,
  type EvaluationBatch,
  type EvaluationPage,
  type EvaluationReport,
  type EvaluationSuite,
} from "@/lib/api/evaluations";

const labels: Record<string, string> = {
  queued: "待执行",
  running: "执行中",
  cancelling: "正在取消",
  completed: "已结束",
  cancelled: "已取消",
  failed: "未通过",
  passed: "通过",
  error: "执行异常",
  pending: "待执行",
};
function batchLabel(batch: EvaluationBatch) {
  return batch.status === "failed" ? "考核异常结束" : labels[batch.status] || batch.status;
}
function problem(code: string) {
  return (
    (
      {
        evaluation_config_changed: "员工配置已改变，剩余考题停止执行。请用新配置发起考核。",
        actor_session_invalid: "发起考核的授权已失效。请重新登录后发起新的考核。",
        grading_failed: "评分未能完成，原始答卷保留。",
      } as Record<string, string>
    )[code] || `执行异常：${code}`
  );
}
const date = (value: string) => new Date(value).toLocaleString("zh-CN");
const offsetValue = (value: string) => (/^\d+$/.test(value) ? Number(value) : 0);

export function EmployeeEvaluations({ agentId, ready }: { agentId: string; ready: boolean }) {
  const [view, setView] = useQueryState("assessment", "");
  const [logCase, setLogCase] = useQueryState("log_case", "");
  const [rawOffset, setOffset] = useQueryState("exam_offset", "0");
  const [rawCaseOffset, setCaseOffset] = useQueryState("case_offset", "0");
  const offset = offsetValue(rawOffset),
    caseOffset = offsetValue(rawCaseOffset);
  const [suites, setSuites] = useState<EvaluationSuite[] | null>(null);
  const [list, setList] = useState<EvaluationPage<EvaluationBatch> | null>(null);
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [count, setCount] = useState("5");
  const [revision, setRevision] = useState(0);
  const command = useRef({ key: crypto.randomUUID(), count: "5", suite: "" });
  const { failure, setError } = useFailureState();
  const { failure: suiteFailure, setError: setSuiteError } = useFailureState();
  const operation = useSaveOperation();
  useEffect(() => {
    const controller = new AbortController();
    void evaluationSuites(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) {
          setSuites(value);
          setSuiteError("");
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) setSuiteError(error);
      });
    return () => controller.abort();
  }, [setSuiteError, revision]);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        if (view === "new") return;
        if (view) {
          const data = await evaluationReport(view, caseOffset, controller.signal);
          if (controller.signal.aborted) return;
          setReport(data);
          if (activeEvaluation(data.batch.status)) timer = setTimeout(() => void load(), 1500);
        } else {
          const data = await evaluationList(agentId, offset, controller.signal);
          if (controller.signal.aborted) return;
          setList(data);
          if (data.items.some((item) => activeEvaluation(item.status)))
            timer = setTimeout(() => void load(), 1500);
        }
        setError("");
      } catch (error) {
        if (!controller.signal.aborted) setError(error);
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [agentId, view, offset, caseOffset, revision, setError]);
  const go = (next: string) => {
    setView(next || null);
    operation.clearError();
    setError("");
  };
  const start = async () => {
    const suite = suites?.[0];
    if (!suite) return;
    if (command.current.count !== count || command.current.suite !== suite.id)
      command.current = { key: crypto.randomUUID(), count, suite: suite.id };
    try {
      const result = await operation.run(() =>
        createEvaluation(agentId, suite.id, Number(count), command.current.key),
      );
      command.current = { key: crypto.randomUUID(), count, suite: suite.id };
      setReport(null);
      setCaseOffset(null);
      go(result.id);
    } catch (error) {
      operation.setError(error);
    }
  };
  const retry = () => setRevision((n) => n + 1);
  const errorNotice = (
    <>
      <FailureNotice
        failure={suiteFailure}
        context={{ operation: "initial-read", resource: "evaluation" }}
        actions={[{ label: "重新加载题库", kind: "retry", onClick: retry }]}
      />
      <FailureNotice
        failure={failure}
        context={{ operation: "initial-read", resource: "evaluation" }}
        actions={[{ label: "重新加载", kind: "retry", onClick: retry }]}
      />
      <FailureNotice
        failure={operation.failure}
        context={{ operation: "mutation", resource: "evaluation" }}
      />
    </>
  );
  const back = (
    <Button variant="ghost" size="sm" onClick={() => go("")}>
      <ArrowLeft />
      返回考核列表
    </Button>
  );
  if (view === "new")
    return (
      <div className="space-y-5">
        {back}
        {errorNotice}
        <PageHeading
          headingLevel={2}
          title="发起员工考核"
          description="先确认考核内容与范围，再开始执行。"
        />
        {!suites ? (
          !suiteFailure && <p role="status">正在读取题库…</p>
        ) : !suites.length ? (
          <EmptyState text="尚未接入题库" />
        ) : (
          <form
            className="max-w-2xl space-y-5"
            onSubmit={(event) => {
              event.preventDefault();
              void start();
            }}
          >
            <div className="space-y-2">
              <p className="text-sm font-medium">考核项目</p>
              <p className="rounded-control bg-muted p-3 text-sm">
                {suites[0].name} · {suites[0].category}
              </p>
              <p className="text-xs text-text-muted">
                固定题库 {suites[0].total} 题；每题独立执行，答案不提供给员工。
              </p>
            </div>
            <div className="max-w-xs space-y-2">
              <label className="text-sm font-medium" htmlFor="assessment-count">
                本次抽样题数
              </label>
              <Input
                id="assessment-count"
                type="number"
                min={1}
                max={suites[0].total}
                required
                value={count}
                disabled={operation.saving}
                onChange={(event) => setCount(event.target.value)}
              />
            </div>
            <p className="rounded-control bg-muted p-3 text-sm text-text-muted">
              {suites[0].scope}
            </p>
            <p className="text-xs text-text-muted">
              使用当前配置开始考核；配置或资源依据改变时，剩余考题停止。执行会调用实际模型并消耗用量。
            </p>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={!ready || operation.saving}>
                {operation.saving ? "正在受理…" : "开始考核"}
              </Button>
              <Button
                variant="outline"
                type="button"
                disabled={operation.saving}
                onClick={() => go("")}
              >
                取消
              </Button>
            </div>
          </form>
        )}
      </div>
    );
  if (view) {
    const current = report?.batch.id === view ? report : null;
    return (
      <div className="space-y-5">
        {back}
        {errorNotice}
        {!current ? (
          !failure && <p role="status">正在读取考核记录…</p>
        ) : (
          <>
            <PageHeading
              headingLevel={2}
              title={current.batch.name}
              description={`${batchLabel(current.batch)} · 配置 v${current.batch.agent_revision} · ${current.batch.model_id}`}
              actions={
                activeEvaluation(current.batch.status) && (
                  <Button
                    variant="outline"
                    disabled={operation.saving}
                    onClick={() =>
                      void operation
                        .run(() => cancelEvaluation(view))
                        .then((result) => {
                          if (result) retry();
                        })
                        .catch(operation.setError)
                    }
                  >
                    取消考核
                  </Button>
                )
              }
            />
            {current.batch.error_code && (
              <p role="status" className="text-sm text-danger">
                {problem(current.batch.error_code)}
              </p>
            )}
            <p className="text-sm tabular-nums">
              完成 {current.batch.completed} / {current.batch.total} 题 · 通过{" "}
              {current.batch.passed} · 未通过 {current.batch.failed} · 异常 {current.batch.errors} ·
              取消 {current.batch.cancelled}
            </p>
            <p className="text-xs text-text-muted">
              已评分通过率：
              {current.batch.pass_rate === null
                ? "暂无评分"
                : `${(current.batch.pass_rate * 100).toFixed(1)}%（${current.batch.passed}/${current.batch.scored}）`}
              。 运行异常单独统计，不计为答题错误。
            </p>
            <p className="rounded-control bg-muted p-3 text-sm text-text-muted">
              {current.batch.scope}
            </p>
            <details className="text-xs text-text-muted">
              <summary>版本与测试依据</summary>
              <dl className="mt-3 grid gap-2 [overflow-wrap:anywhere]">
                <dt>题库 SHA256</dt>
                <dd>{current.batch.suite_version}</dd>
                <dt>评分器</dt>
                <dd>{current.batch.grader_version}</dd>
                <dt>员工配置摘要</dt>
                <dd>{current.batch.configuration_hash}</dd>
                <dt>创建时间</dt>
                <dd>{date(current.batch.created_at)}</dd>
              </dl>
            </details>
            <div className="divide-y divide-border">
              {current.cases.items.map((item) => (
                <details key={item.id} className="py-4 text-sm">
                  <summary className="flex flex-wrap items-center justify-between gap-2">
                    <span>
                      第 {item.ordinal} 题 · {item.question_id}
                    </span>
                    <span className="text-text-muted">{labels[item.status] || item.status}</span>
                  </summary>
                  <div className="mt-4 space-y-3">
                    <p className="text-xs text-text-muted">
                      执行状态：{item.run_status || "尚未受理"} · Run {item.run_id || "—"}
                    </p>
                    {item.run_id && (
                      <Button variant="ghost" size="sm" onClick={() => setLogCase(item.id)}>
                        查看执行详情
                      </Button>
                    )}
                    <details>
                      <summary>题目与函数说明</summary>
                      <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-control bg-muted p-3 text-xs [overflow-wrap:anywhere]">
                        {item.question}
                      </pre>
                    </details>
                    <p className="font-medium">员工答卷</p>
                    <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-control bg-muted p-3 text-xs [overflow-wrap:anywhere]">
                      {item.answer || "尚未取得答卷"}
                    </pre>
                    {item.grading && (
                      <>
                        <p className="font-medium">评分依据</p>
                        <p>
                          {item.grading.valid
                            ? "函数与参数满足本题评分规则。"
                            : item.grading.error.join("\n")}
                        </p>
                        <p className="text-xs text-text-muted">{item.grading.error_type}</p>
                      </>
                    )}
                    {item.expected && (
                      <details>
                        <summary>可接受答案</summary>
                        <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-control bg-muted p-3 text-xs">
                          {JSON.stringify(item.expected, null, 2)}
                        </pre>
                      </details>
                    )}
                    {item.error_code && <p className="text-danger">{problem(item.error_code)}</p>}
                  </div>
                </details>
              ))}
            </div>
            {current.cases.total > 20 && (
              <Pagination
                offset={caseOffset}
                total={current.cases.total}
                onChange={(value) => setCaseOffset(String(value))}
              />
            )}
            {!activeEvaluation(current.batch.status) && (
              <Button
                variant="outline"
                onClick={() => {
                  setCount(String(current.batch.total));
                  go("new");
                }}
              >
                按相同题库与题数再次考核
              </Button>
            )}
            {logCase && (
              <ExecutionLogDialog
                target={{ agentId, batchId: current.batch.id, caseId: logCase }}
                onClose={() => setLogCase("")}
              />
            )}
          </>
        )}
      </div>
    );
  }
  return (
    <div className="space-y-5">
      <PageHeading
        headingLevel={2}
        title="员工考核"
        description="查看专项考核记录、员工答卷和评分依据。"
        actions={
          <Button disabled={!ready} onClick={() => go("new")}>
            <Plus />
            发起考核
          </Button>
        }
      />
      {!ready && <p className="text-sm text-text-muted">员工需启用并配置模型后才能发起考核。</p>}
      {errorNotice}
      {!list ? (
        !failure && <p role="status">正在读取考核记录…</p>
      ) : !list.items.length ? (
        <EmptyState
          text="尚未进行考核"
          description="从 BFCL 工具调用专项开始检查员工表现。"
          icon={<ClipboardCheck aria-hidden="true" />}
        />
      ) : (
        <ul className="divide-y divide-border">
          {list.items.map((item) => (
            <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-4">
              <div className="min-w-0">
                <p className="text-sm font-medium">{item.name}</p>
                <p className="mt-1 text-xs text-text-muted">
                  {date(item.created_at)} · 配置 v{item.agent_revision} · {item.total} 题
                </p>
                <p className="mt-2 text-sm">
                  {batchLabel(item)} · 完成 {item.completed}/{item.total}
                  {item.scored > 0 && ` · 通过 ${item.passed}/${item.scored}`}
                  {item.errors > 0 && ` · 异常 ${item.errors}`}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setReport(null);
                  setCaseOffset(null);
                  go(item.id);
                }}
              >
                {activeEvaluation(item.status) ? "查看进度" : "查看报告"}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {list && list.total > 20 && (
        <Pagination
          offset={offset}
          total={list.total}
          onChange={(value) => setOffset(String(value))}
        />
      )}
    </div>
  );
}

function Pagination({
  offset,
  total,
  onChange,
}: {
  offset: number;
  total: number;
  onChange: (value: number) => void;
}) {
  return (
    <nav aria-label="考核记录分页" className="flex flex-wrap items-center justify-end gap-3">
      <Button
        size="sm"
        variant="ghost"
        disabled={!offset}
        onClick={() => onChange(Math.max(0, offset - 20))}
      >
        上一页
      </Button>
      <span className="text-xs text-text-muted">
        {Math.floor(offset / 20) + 1} / {Math.ceil(total / 20)}
      </span>
      <Button
        size="sm"
        variant="ghost"
        disabled={offset + 20 >= total}
        onClick={() => onChange(offset + 20)}
      >
        下一页
      </Button>
    </nav>
  );
}
