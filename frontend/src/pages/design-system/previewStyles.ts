/** Shared catalogue presentation; all classes are statically discoverable by Tailwind. */
export const styles = {
  panel: "form-panel",
  panelTitle:
    "mb-5 flex flex-wrap justify-between gap-2 [&>h3]:font-semibold [&>span]:text-xs [&>span]:text-text-muted",
  caption: "mt-3 text-xs leading-relaxed text-text-muted",
  foundationGrid: "connection-grid",
  navPreview: "mb-4 w-(--os-navigation-width) max-w-full rounded-panel bg-canvas p-2",
  navigationTokens:
    "grid gap-3 text-sm [&>div]:flex [&>div]:flex-wrap [&>div]:justify-between [&>div]:gap-2 [&_dt]:text-text-muted [&_dd]:tabular-nums",
  accountPreview: "mt-4 w-(--os-navigation-width) max-w-full border-t border-border pt-2",
  headingVariants:
    "mt-5 border-t border-border pt-4 [&>summary]:text-xs [&>summary]:text-text-muted open:[&>summary]:mb-6",
  controls: "flex flex-wrap items-center gap-3",
  field: "mb-4 grid gap-2 text-sm [&>[data-slot=select-trigger]]:w-full",
  error: "flex items-center gap-1.5 text-xs text-danger",
  switchLine: "flex items-center justify-between gap-3 whitespace-nowrap text-sm",
  agentToolbar: "mb-5 flex flex-col justify-between gap-5 sm:flex-row",

  toolbarActions: "flex items-center gap-6",
  agents: "employee-grid",

  annotation: "mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-text-muted",
  statuses:
    "mb-5 flex flex-wrap gap-3 [&>span]:flex [&>span]:items-center [&>span]:gap-1.5 [&>span]:rounded-small [&>span]:px-2.5 [&>span]:py-1 [&>span]:text-xs [&_i]:size-1 [&_i]:rounded-full [&_i]:bg-current",
  feedbackGrid: "capability-grid",
  stateCard:
    "flex flex-col items-start gap-3 p-6 [&>svg]:text-text-muted [&>strong]:text-sm [&>p]:text-xs [&>p]:text-text-muted [&>button]:mt-auto",
  skeleton: "size-8 rounded-control bg-muted",
  skeletonLine: "h-2 w-4/5 rounded-small bg-muted",
} as const;
