export default {
  page: "workspace-region min-h-[100dvh] bg-canvas",
  topbar:
    "page-gutters min-h-[calc(var(--os-space-6)_*_2)] flex items-center gap-(--os-space-4) [border-bottom:1px_solid_var(--os-border)] bg-surface text-[length:var(--os-text-caption)] [&_a]:[font-weight:var(--os-weight-heading)] [&_>_span]:text-text-muted max-[600px]:gap-(--os-space-2)",
  brandLink: "[--brand-logo-scale:0.85] flex items-center shrink-0",
  designLink:
    "[margin-inline-start:auto] py-(--os-space-1) px-(--os-space-2) rounded-control text-text-muted [&:hover]:text-text [&:hover]:bg-muted",
  main: "page-frame py-6",
  topics:
    "flex flex-wrap gap-(--os-space-2) mb-(--os-space-6) [&_a]:py-(--os-space-1) [&_a]:px-(--os-space-3) [&_a]:rounded-control [&_a]:text-text-muted [&_a]:text-[length:var(--os-text-caption)] [&_a:hover]:bg-muted [&_a[aria-current='page']]:text-action [&_a[aria-current='page']]:bg-muted",
  article:
    "py-0 px-(--os-space-6) [&_section]:grid [&_section]:[grid-template-columns:auto_minmax(0,_1fr)] [&_section]:gap-(--os-space-4) [&_section]:py-(--os-space-6) [&_section_+_section]:[border-top:1px_solid_var(--os-border)] [&_h2]:text-[length:var(--os-text-title)] [&_h2]:[font-weight:var(--os-weight-heading)] [&_p]:article-measure [&_p]:mt-(--os-space-2) [&_p]:text-text-muted [&_p]:leading-[1.9] max-[600px]:px-(--os-space-4)",
  number: "text-action text-[length:var(--os-text-caption)] leading-[2.4] tabular-nums",
  note: "article-measure mt-(--os-space-6) text-text-muted text-[length:var(--os-text-caption)] leading-[1.8]",
};
