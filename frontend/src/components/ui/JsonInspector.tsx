import { useState, type CSSProperties } from "react";
import JsonView from "@uiw/react-json-view";
import { ChevronDown } from "lucide-react";
import { Button } from "./Button";

const inspectorTheme = {
  "--w-rjv-background-color": "var(--os-muted)",
  "--w-rjv-color": "var(--os-text)",
  "--w-rjv-key-string": "var(--os-text)",
  "--w-rjv-key-number": "var(--os-info)",
  "--w-rjv-line-color": "var(--os-border)",
  "--w-rjv-arrow-color": "var(--os-text-muted)",
  "--w-rjv-info-color": "var(--os-text-muted)",
  "--w-rjv-curlybraces-color": "var(--os-text-muted)",
  "--w-rjv-brackets-color": "var(--os-text-muted)",
  "--w-rjv-colon-color": "var(--os-text-muted)",
  "--w-rjv-quotes-color": "var(--os-text-muted)",
  "--w-rjv-quotes-string-color": "var(--os-success)",
  "--w-rjv-type-string-color": "var(--os-success)",
  "--w-rjv-type-int-color": "var(--os-info)",
  "--w-rjv-type-float-color": "var(--os-info)",
  "--w-rjv-type-boolean-color": "var(--os-brand)",
  "--w-rjv-type-null-color": "var(--os-text-muted)",
  "--w-rjv-type-undefined-color": "var(--os-text-muted)",
  "--w-rjv-ellipsis-color": "var(--os-text-muted)",
  "--w-rjv-copied-color": "var(--os-text-muted)",
  "--w-rjv-copied-success-color": "var(--os-success)",
} as CSSProperties;

/** Read-only evidence viewer. JSON strings are parsed only when they contain an object or array. */
export function JsonInspector({
  value,
  foldReasoning = false,
}: {
  value: unknown;
  foldReasoning?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [copyState, setCopyState] = useState("");
  let parsed = value;
  if (typeof value === "string" && /^\s*[[{]/.test(value)) {
    try {
      parsed = JSON.parse(value);
    } catch {
      // A truncated JSON preview remains text; it is not complete structured evidence.
    }
  }
  if (parsed === null || typeof parsed !== "object")
    return (
      <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-control bg-muted p-3 text-xs leading-6 [overflow-wrap:anywhere]">
        {parsed === undefined ? "未提供" : String(parsed)}
      </pre>
    );
  return (
    <div className="min-w-0 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="xs" onClick={() => setExpanded((current) => !current)}>
          {expanded ? "折叠层级" : "展开全部"}
        </Button>
        <Button
          variant="ghost"
          size="xs"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(JSON.stringify(parsed, null, 2));
              setCopyState("已复制");
            } catch {
              setCopyState("复制失败，请选择文本复制");
            }
          }}
        >
          复制 JSON
        </Button>
        <span className="text-xs text-text-muted" role="status">
          {copyState}
        </span>
      </div>
      <div className="max-h-[28rem] overflow-auto rounded-control bg-muted p-3 text-xs leading-6">
        <JsonView
          key={String(expanded)}
          value={parsed}
          collapsed={expanded ? false : 2}
          displayDataTypes={false}
          shortenTextAfterLength={180}
          highlightUpdates={false}
          style={inspectorTheme}
        >
          {foldReasoning && (
            <JsonView.String
              render={(_props, { type, value: text, keyName }) => {
                if (
                  type === "value" &&
                  typeof text === "string" &&
                  ["reasoning_content", "reasoning", "thinking"].includes(String(keyName))
                )
                  return <ReasoningValue value={text} />;
                return undefined;
              }}
            />
          )}
          <JsonView.Arrow
            as="button"
            type="button"
            aria-label="展开或折叠 JSON 节点"
            className="rounded-small p-0.5 focus-visible:outline-2 focus-visible:outline-focus"
          >
            <ChevronDown size={12} aria-hidden="true" />
          </JsonView.Arrow>
        </JsonView>
      </div>
    </div>
  );
}

function ReasoningValue({ value }: { value: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <span>
      <Button
        variant="ghost"
        size="xs"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        {expanded ? "收起思考字段" : `展开思考字段（${value.length.toLocaleString()} 字符）`}
      </Button>
      {expanded && (
        <span className="block whitespace-pre-wrap text-xs leading-6 [overflow-wrap:anywhere]">
          {value}
        </span>
      )}
    </span>
  );
}
