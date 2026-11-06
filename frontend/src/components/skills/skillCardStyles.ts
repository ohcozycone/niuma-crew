export default {
  card: "resource-card-content",
  top: "flex items-center justify-between gap-(--os-space-2)",
  footer: "text-[length:var(--os-text-caption)]",
  icon: "grid [place-items:center] w-8.5 h-8.5 rounded-control bg-muted text-text-muted",
  title:
    "mt-(--os-space-4) text-[length:var(--os-text-title)] [font-weight:var(--os-weight-heading)] [&_button]:text-left [&_button:hover]:[text-decoration:underline] [&_button:hover]:[text-underline-offset:4px]",
  description:
    "my-[var(--os-space-3)_var(--os-space-4)] min-h-[3.4em] text-[length:var(--os-text-support)] text-text-muted leading-[1.7]",
  selection:
    "inline-flex items-center gap-(--os-space-2) min-h-(--os-control-small) [&_input]:w-4 [&_input]:h-4 [&_input]:[accent-color:var(--os-action)]",
  usage: "text-text-muted min-h-(--os-control-small) [&:not(:disabled):hover]:text-action",
  details:
    "mt-(--os-space-4) pt-(--os-space-4) [border-top:1px_solid_var(--os-border)] text-[length:var(--os-text-support)] leading-[1.7] [&_div_+_div]:mt-(--os-space-3) [&_dt]:text-text-muted [&_dt]:mb-(--os-space-1) [&_dd]:m-0 [&_dd]:[overflow-wrap:anywhere]",
};
