export default {
  heading:
    "flex flex-wrap items-start gap-[var(--os-heading-stack-gap)_var(--os-heading-gap)] mb-(--os-heading-content-gap) [&[data-meta-only]>div:first-child]:min-w-0 [&[data-meta-only]>div:first-child]:basis-0",
  copy: "flex-[1_1_var(--os-heading-copy-min)] min-w-[min(100%,var(--os-heading-copy-min))]",
  title:
    "w-[fit-content] max-w-full m-0 text-(--os-type-page-color) text-[length:var(--os-type-page-size)] [font-weight:var(--os-type-page-weight)] leading-[var(--os-type-page-leading)] tracking-[var(--os-type-page-tracking)] [overflow-wrap:anywhere] @max-[640px]/page:text-[length:var(--os-type-section-size)]",
  description:
    "mt-(--os-heading-description-gap) mx-0 mb-0 text-(--os-type-description-color) text-[length:var(--os-type-description-size)] [font-weight:var(--os-type-description-weight)] leading-[var(--os-type-description-leading)] tracking-[var(--os-type-description-tracking)] [overflow-wrap:anywhere]",
  actions:
    "flex max-w-full items-center flex-wrap justify-end gap-(--os-heading-actions-gap) min-w-0 @max-[640px]/page:justify-start",
  meta: "text-(--os-type-caption-color) text-[length:var(--os-type-caption-size)] [font-weight:var(--os-type-caption-weight)] leading-[var(--os-type-caption-leading)] tracking-[var(--os-type-caption-tracking)] [overflow-wrap:anywhere]",
};
