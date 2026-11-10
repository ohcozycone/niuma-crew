export default {
  page: "page-frame pt-6 pb-12 [color:var(--os-text)] [font-family:var(--font-sans,_system-ui,_sans-serif)] ",
  eyebrow:
    "eyebrow [color:var(--os-text-muted)] text-[length:10px] tracking-[0.18em] font-[600] mt-0 mx-0 mb-3",
  back: "text-text-muted text-[length:var(--os-text-caption)] whitespace-nowrap [text-decoration:none]",
  toolbar:
    "[border-top:1px_solid_var(--os-border)] flex gap-2 items-center pt-5 px-0 pb-6 [color:var(--os-text-muted)] text-[length:12px] flex-wrap [&_>_span:first-child]:mr-2.5 [&_button]:[border:1px_solid_transparent] [&_button]:bg-transparent [&_button]:[color:inherit] [&_button]:py-[7px] [&_button]:px-[11px] [&_button]:rounded-control [&_button]:flex [&_button]:items-center [&_button]:gap-1.5 [&_button]:text-[length:12px] [&_button]:cursor-pointer [&_button[aria-pressed='true']]:[background:var(--os-selected)] [&_button[aria-pressed='true']]:[color:var(--os-text)] [&_button[aria-pressed='true']]:[border-color:var(--os-border)] [&_i]:w-3 [&_i]:h-3 [&_i]:rounded-full [&_i]:[border:1px_solid_var(--os-border)]",
  zoom: "[&_button]:[border:1px_solid_transparent] [&_button]:bg-transparent [&_button]:[color:inherit] [&_button]:py-[7px] [&_button]:px-[11px] [&_button]:rounded-control [&_button]:flex [&_button]:items-center [&_button]:gap-1.5 [&_button]:text-[length:12px] [&_button]:cursor-pointer [&_button[aria-pressed='true']]:[background:var(--os-selected)] [&_button[aria-pressed='true']]:[color:var(--os-text)] [&_button[aria-pressed='true']]:[border-color:var(--os-border)] flex",
  note: "ml-auto [color:var(--os-text-muted)] text-[length:11px] max-[760px]:hidden",
  grid: "employee-grid",
  card: "min-w-0",
  portrait:
    "w-full [aspect-ratio:1] rounded-panel [border:1px_solid_var(--os-border)] p-4.5 block cursor-pointer overflow-hidden [transition:border-color_0.15s] [&:hover]:[border-color:var(--os-focus)] [&:hover]:[outline:2px_solid_var(--os-focus)] [&:hover]:[outline-offset:2px] [&:focus-visible]:[border-color:var(--os-focus)] [&:focus-visible]:[outline:2px_solid_var(--os-focus)] [&:focus-visible]:[outline-offset:2px] max-[760px]:p-1.5",
  cardTitle:
    "flex justify-between items-center pt-[15px] px-0.5 pb-0 gap-2 [&_h2]:text-[length:15px] [&_h2]:font-[550] [&_h2]:m-0 [&_a]:text-[length:11px] [&_a]:[color:var(--os-brand-text)] [&_a]:[text-decoration:none] max-[420px]:items-start max-[420px]:flex-col max-[420px]:gap-[5px] max-[420px]:[&_h2]:text-[length:14px]",
  identifier:
    "mt-[5px] mx-0.5 mb-0 [color:var(--os-text-muted)] text-[length:10px] tracking-[0.03em]",
  samples:
    "h-33 flex [align-items:end] gap-6 pt-3 px-0.5 pb-0 [border-bottom:1px_solid_var(--os-border)] [&_>_div]:flex [&_>_div]:flex-col [&_>_div]:items-center [&_>_div]:gap-[7px] [&_span]:text-[length:9px] [&_span]:[color:var(--os-text-muted)] [&_span]:pb-3 max-[760px]:gap-2.5 max-[760px]:[&_>_div:last-child]:hidden max-[760px]:h-23",
  detail: "mt-12",
  detailTitle:
    "flex justify-between items-center pt-0 px-0 pb-4.5 [&_h2]:text-[length:19px] [&_h2]:font-[500] [&_h2]:m-0 [&_.eyebrow]:mb-2",
  usage:
    "[&_h2]:text-[length:19px] [&_h2]:font-[500] [&_h2]:m-0 grid [grid-template-columns:1fr_1.15fr] gap-10 [border-top:1px_solid_var(--os-border)] mt-11 pt-8.5 [&_p:last-child]:[color:var(--os-text-muted)] [&_p:last-child]:text-[length:12px] [&_p:last-child]:leading-[1.7] [&_pre]:overflow-auto [&_pre]:[background:var(--os-muted)] [&_pre]:[border:1px_solid_var(--os-border)] [&_pre]:rounded-panel [&_pre]:py-5 [&_pre]:px-6 [&_pre]:m-0 [&_pre]:text-[length:12px] [&_pre]:leading-[1.7] [&_pre]:[color:var(--os-text)] max-[760px]:[grid-template-columns:1fr] max-[760px]:gap-5",
  viewport: "[border:1px_solid_var(--os-border)] rounded-panel w-full h-90 overflow-auto",
  hint: "[color:var(--os-text-muted)] text-[length:11px] mt-2.5 mx-0 mb-0",
  checker:
    "[background-image:linear-gradient(45deg,_var(--os-border)_25%,_transparent_25%),_linear-gradient(-45deg,_var(--os-border)_25%,_transparent_25%),_linear-gradient(45deg,_transparent_75%,_var(--os-border)_75%),_linear-gradient(-45deg,_transparent_75%,_var(--os-border)_75%)] [background-size:18px_18px] [background-position:0_0,_0_9px,_9px_-9px,_-9px_0]",
};
