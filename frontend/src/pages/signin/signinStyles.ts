export default {
  page: "m-0 min-h-[100svh] py-4 px-3 grid [place-items:center] bg-(--login-bg) [color-scheme:inherit] text-text leading-[normal] [font-family:-apple-system,_BlinkMacSystemFont,_'PingFang_SC',_sans-serif] [-webkit-font-smoothing:antialiased] [-webkit-user-select:none] select-none [&_:where(button,_input)]:[font:inherit] [&_input]:[-webkit-user-select:text] [&_input]:select-text [&_textarea]:[-webkit-user-select:text] [&_textarea]:select-text [&_button]:cursor-pointer [&_button:disabled]:cursor-wait [&_button:disabled]:[opacity:0.65] [&_[hidden]]:hidden! [&_button:focus-visible]:[outline:3px_solid_var(--login-ring)] [&_button:focus-visible]:[outline-offset:4px] [&_.github:disabled]:cursor-not-allowed [&_.github:disabled]:[opacity:0.45] [&_.github[aria-busy='true']]:cursor-wait [&_.github[aria-busy='true']]:[opacity:0.65] [&_input::selection]:bg-(--login-selection) [&_input::selection]:text-text",
  shell:
    "[--w:820px] [--h:560px] [--scale:1] [--box-w:822px] [--box-h:562px] [--floor:218px] [--body-y:244px] relative w-(--box-w) h-(--box-h) [border:1px_solid_var(--login-border)] rounded-[14px] overflow-hidden bg-(--login-scene)",
  canvas:
    "relative w-(--w) h-(--h) [transform:scale(var(--scale))] [transform-origin:0_0] overflow-hidden isolate",
  "scene-header":
    "absolute top-[23px] left-7.5 right-7.5 flex items-center gap-[13px] text-text-muted text-[length:10px] tracking-[0.09em] [z-index:0] [&_i]:w-[5px] [&_i]:h-[5px] [&_i]:bg-brand [&_i]:rounded-full [&_b]:font-[650] [&_b]:tracking-[0.12em] [&_em]:h-[11px] [&_em]:w-px [&_em]:bg-(--login-input) [&_span]:tracking-[0.02em] max-[700px]:top-[19px] max-[700px]:left-6 max-[700px]:right-6 max-[700px]:text-[length:8px] max-[700px]:gap-[9px] [&_.os-theme-switcher]:ml-auto [&_.os-theme-switcher]:tracking-[normal] [@media(pointer:_coarse)]:[&_.os-theme-switcher]:my-[-6px]",
  "brand-stage":
    "absolute top-[65px] left-[50%] [transform:translateX(-50%)] w-[min(640px,_calc(100%_-_64px))] [aspect-ratio:592/150] [z-index:1] pointer-events-none max-[700px]:top-[57px] max-[700px]:w-[calc(100%_-_40px)]",
  perch:
    "[--logo-ink:var(--os-text)] block w-full h-full overflow-visible [&_svg]:[--logo-ink:var(--os-text)] [&_svg]:block [&_svg]:w-full [&_svg]:h-full [&_svg]:overflow-visible",
  foreground:
    "absolute top-(--floor) bottom-0 left-0 right-0 [z-index:2] pointer-events-none [&_svg]:block [&_svg]:w-full [&_svg]:h-full [&_svg]:overflow-visible",
  "scene-body":
    "absolute top-(--body-y) left-[50%] [transform:translateX(-50%)] w-[min(640px,_calc(100%_-_64px))] py-0 px-2 grid [grid-template-columns:minmax(0,_1fr)_var(--login-column)] gap-x-(--login-gutter) [z-index:3] max-[700px]:w-[calc(100%_-_48px)] max-[700px]:p-0 max-[700px]:[grid-template-columns:minmax(0,_1fr)] max-[700px]:gap-y-[17px]",
  copy: "pt-[7px] [&_h2]:text-[length:32px] [&_h2]:font-[500] [&_h2]:tracking-[-1.8px] [&_h2]:leading-[1.36] [&_h2]:mt-0 [&_h2]:mx-0 [&_h2]:mb-[19px] [&_h2_span]:text-brand-text [&_p]:text-[length:12px] [&_p]:leading-[1.95] [&_p]:text-text-muted [&_p]:m-0 max-[700px]:p-0 max-[700px]:[&_h2]:text-[length:22px] max-[700px]:[&_h2]:leading-[1.4] max-[700px]:[&_h2]:m-0 max-[700px]:[&_h2]:tracking-[-1px] max-[700px]:[&_h2_br]:hidden max-[700px]:[&_p]:hidden",
  form: "min-w-0 [&_h1]:text-[length:18px] [&_h1]:leading-[22px] [&_h1]:tracking-[-0.6px] [&_h1]:font-[600] [&_h1]:text-(--login-title) [&_h1]:m-0 max-[700px]:[&_h1]:text-[length:20px] max-[700px]:[&_h1]:leading-[24px]",
  "form-heading": "mb-3 max-[700px]:mb-3",
  credentials: "min-w-0 border-0 m-0 p-0",
  field:
    "flex items-center gap-3 min-h-9 [border-bottom:1px_solid_var(--login-input)] text-[length:11px] leading-[14px] text-text-muted mt-0 mx-0 mb-1.5 [&_>_span]:[flex:0_0_auto] [&_input]:block [&_input]:min-w-0 [&_input]:flex-1 [&_input]:w-full [&_input]:m-0 [&_input]:h-8 [&_input]:border-0 [&_input]:rounded-none [&_input]:bg-transparent [&_input]:py-0 [&_input]:px-0.5 [&_input]:text-text [&_input]:text-[length:13px] [&_input:focus-visible]:[outline:0] rounded-small [corner-shape:round] transition-[border-color,box-shadow] focus-within:ring-[3px] focus-within:ring-field-focus/50 [&:focus-within]:border-field-focus [&:last-of-type]:mb-0 [&:has(input[aria-invalid='true'])]:border-danger has-[[aria-invalid=true]]:focus-within:ring-danger/20 max-[700px]:text-[length:11px] max-[700px]:leading-[15px] max-[700px]:min-h-10 max-[700px]:mb-1.5 max-[700px]:[&_input]:text-[length:16px] max-[700px]:[&_input]:h-9.5",
  enter:
    "flex items-center justify-between w-full h-9 border-0 rounded-control bg-action text-action-text py-0 px-3 mt-0 text-[length:13px] font-[500] [&:hover]:bg-action-hover [&_em]:text-[length:18px] [&_em]:[font-style:normal] max-[700px]:text-[length:14px] max-[700px]:h-10",
  "other-signin": "mt-3.5 text-center",
  "other-signin-label":
    "flex items-center gap-3 text-text-muted text-[length:10px] leading-[14px] [&::before]:[content:''] [&::before]:flex-1 [&::before]:[border-top:1px_solid_var(--os-border)] [&::after]:[content:''] [&::after]:flex-1 [&::after]:[border-top:1px_solid_var(--os-border)]",
  "other-signin-options": "flex items-center justify-between gap-4 mt-2",
  github:
    "github relative grid [place-items:center] w-9 h-9 p-0 m-0 rounded-full bg-transparent text-text [border:1px_solid_var(--os-border)] [&_svg]:w-5 [&_svg]:h-5 [&_svg]:[fill:currentColor] [&:hover:not(:disabled)]:bg-muted [&:hover:not(:disabled)]:[border-color:var(--login-input)] [&[aria-busy='true']_svg]:invisible [&[aria-busy='true']::after]:[content:''] [&[aria-busy='true']::after]:absolute [&[aria-busy='true']::after]:w-4 [&[aria-busy='true']::after]:h-4 [&[aria-busy='true']::after]:[border:2px_solid_var(--os-border)] [&[aria-busy='true']::after]:[border-top-color:currentColor] [&[aria-busy='true']::after]:rounded-full [&[aria-busy='true']::after]:[animation:github-pending_0.8s_linear_infinite] motion-reduce:[&[aria-busy='true']::after]:[animation:none] max-[700px]:w-10 max-[700px]:h-10 [@media(pointer:_coarse)]:w-11 [@media(pointer:_coarse)]:h-11",
  guest:
    "block border-0 bg-transparent text-text-muted m-0 py-1 px-2.5 text-[length:11px] leading-[16px] [&_span]:pl-1.5 max-[700px]:text-[length:12px]",
  "feedback-slot": "h-(--login-feedback) pt-0.5",
  status:
    "text-[length:10px] leading-[12px] text-action m-0 [&.error]:text-danger [overflow-wrap:anywhere]",
  caption:
    "absolute bottom-[19px] left-[max(38px,_calc((100%_-_624px)_/_2))] text-[length:9px] tracking-[0.03em] text-text-muted [z-index:3] max-[700px]:hidden",
};
