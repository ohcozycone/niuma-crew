export default {
  card: "[--agent-portrait-width:104px] [--agent-portrait-gap:var(--os-card-gap)] @max-[320px]/agent:[--agent-portrait-width:88px] @max-[320px]/agent:[--agent-portrait-gap:var(--os-card-gap-sm)] @max-[320px]/agent:px-(--os-space-4) @max-[320px]/agent:pt-(--os-space-4) @max-[320px]/agent:[grid-template-columns:minmax(0,_1fr)] @max-[320px]/agent:gap-0",
  actions:
    "absolute [z-index:1] top-(--os-space-3) right-(--os-space-3) flex items-center gap-(--os-space-1) text-text-muted",
  favorite: "[&[aria-pressed='true']]:text-brand",
  identity:
    "relative min-w-0 min-h-22 mt-(--os-space-6) p-(--os-space-2) pl-[calc(var(--agent-portrait-width)_+_var(--agent-portrait-gap))] rounded-panel bg-transparent [&::before]:[content:''] [&::before]:absolute [&::before]:left-[12px] [&::before]:bottom-5.5 [&::before]:w-[80px] [&::before]:[aspect-ratio:1.45] [&::before]:rounded-[40px_40px_var(--os-radius-control)_var(--os-radius-control)] [&::before]:bg-avatar-bg @max-[320px]/agent:[&::before]:left-[10px] @max-[320px]/agent:[&::before]:bottom-5 @max-[320px]/agent:[&::before]:w-[68px] @max-[320px]/agent:[&::before]:rounded-[34px_34px_var(--os-radius-control)_var(--os-radius-control)]",
  portrait:
    "absolute bottom-0 left-0 w-(--agent-portrait-width) h-28 rounded-control [&_svg]:pointer-events-none [&_svg]:w-full [&_svg]:h-full [&_svg]:object-contain @max-[320px]/agent:h-24",
  nameBlock: "flex flex-col items-start gap-(--os-space-1) min-w-0",
  name: "flex items-center gap-(--os-space-1) max-w-full min-w-0 text-left [&_h3]:text-[length:var(--os-text-title)] [&_h3]:leading-[1.4] [&_h3]:[font-weight:var(--os-weight-heading)] [&_h3]:overflow-hidden [&_h3]:text-ellipsis [&_h3]:whitespace-nowrap [&:not(:disabled):hover_h3]:[text-decoration:underline] [&:not(:disabled):hover_h3]:[text-underline-offset:4px]",
  subtitle:
    "max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-text-muted text-[length:var(--os-text-caption)]",
  status:
    "inline-flex items-center gap-1.5 text-text-muted text-[length:var(--os-text-caption)] whitespace-nowrap [&_i]:w-1.5 [&_i]:h-1.5 [&_i]:rounded-full [&_i]:[background:currentColor] [&[data-status='available']]:text-text-muted [&[data-status='available']_i]:bg-success [&[data-status='unconfigured']]:text-warning",
  description:
    "my-(--os-space-3) h-[3.2em] text-text-muted leading-[1.6] overflow-hidden [display:-webkit-box] [-webkit-line-clamp:2] [-webkit-box-orient:vertical] [overflow-wrap:anywhere]",
  assign: "ml-auto",
  resources: "flex flex-wrap items-center gap-x-(--os-space-3) gap-y-(--os-space-1) min-w-0",
  resource:
    "inline-flex items-center gap-(--os-space-1) text-text-muted text-[length:var(--os-text-caption)] min-h-8 whitespace-nowrap [button&:not(:disabled):hover]:text-text",
  resourceCount: "tabular-nums",
};
