import { FailureNotice } from "@/components/failure/FailureNotice";
import { useEffect } from "react";
import { brand } from "@/lib/brand";
import { cn } from "@/lib/utils";
import { ThemeSwitcher } from "@/components/theme/ThemeSwitcher";
import { Button } from "@/components/ui/Button";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { Form } from "@/components/ui/Form";
import { Field, FieldLabel, FieldControl } from "@/components/ui/Field";
import { signinLogo } from "@/components/brand/wordmarkSource";
import { useSigninForm } from "./useSigninForm";
import { useSigninScene } from "./useSigninScene";
import styles from "./signinStyles";

export function SigninPage() {
  const { rootRef, finish } = useSigninScene();
  const form = useSigninForm(finish);
  useEffect(() => {
    const previous = document.title;
    document.title = `登录 · ${brand.name}`;
    return () => {
      document.title = previous;
    };
  }, []);
  return (
    <main className={styles["page"]} aria-label={`${brand.name} 登录`}>
      <div className={styles["shell"]} id="signin-scene" ref={rootRef} data-motion="static">
        <div className={styles["canvas"]} data-signin-canvas>
          <header className={styles["scene-header"]}>
            <i />
            <b>NIUMACREW</b>
            <em />
            <span>{brand.tagline}</span>
            <ThemeSwitcher className="ml-auto tracking-normal [@media(pointer:coarse)]:-my-1.5" />
          </header>
          <div className={styles["foreground"]} aria-hidden="true">
            <svg data-signin-surface viewBox="0 0 820 342" preserveAspectRatio="none">
              <path
                data-signin-edge
                fill="var(--os-surface)"
                d="M0 10C18 10 36 0 54 0H766C784 0 802 10 820 10V342H0Z"
              />
              <g data-signin-shadows />
            </svg>
          </div>
          <div className={styles["scene-body"]}>
            <section className={styles["copy"]}>
              <h2>
                牛马在岗，
                <br />
                <span>你先松口气。</span>
              </h2>
              <p>
                把重复的工作交给数字员工。
                <br />
                留点时间，做你想做的事。
              </p>
            </section>
            <Form
              className={styles.form}
              aria-labelledby="login-title"
              aria-busy={Boolean(form.pending)}
              onSubmit={(event) => {
                event.preventDefault();
                void form.enter("password");
              }}
              onFocusCapture={form.interact}
              onInput={() => {
                form.interact();
                form.clearFeedback();
              }}
            >
              <header className={styles["form-heading"]}>
                <h1 id="login-title">登录</h1>
              </header>
              <fieldset
                className={styles.credentials}
                aria-label="账号信息"
                disabled={Boolean(form.pending)}
              >
                <Field className={styles.field} name="username">
                  <FieldLabel className="font-normal" nativeLabel={false} render={<span />}>
                    账号
                  </FieldLabel>
                  <FieldControl
                    data-slot="input-group-control"
                    id="username"
                    name="username"
                    autoComplete="username"
                    autoCapitalize="none"
                    spellCheck={false}
                    maxLength={64}
                    aria-required="true"
                    value={form.username}
                    onChange={(event) => form.setUsername(event.target.value)}
                    aria-invalid={form.feedback.fields.includes("username") || undefined}
                    aria-describedby={
                      form.feedback.fields.includes("username") ? "signin-feedback" : undefined
                    }
                  />
                </Field>
                <Field className={cn(styles.field, "mb-0")} name="password">
                  <FieldLabel className="font-normal" nativeLabel={false} render={<span />}>
                    密码
                  </FieldLabel>
                  <FieldControl
                    data-slot="input-group-control"
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    maxLength={128}
                    aria-required="true"
                    value={form.password}
                    onChange={(event) => form.setPassword(event.target.value)}
                    aria-invalid={form.feedback.fields.includes("password") || undefined}
                    aria-describedby={
                      form.feedback.fields.includes("password") ? "signin-feedback" : undefined
                    }
                  />
                </Field>
                <div className={styles["feedback-slot"]}>
                  <div id="signin-feedback" aria-atomic="true">
                    {form.feedback.message && (
                      <FailureNotice
                        failure={form.feedback.failure}
                        error={form.feedback.message}
                        description={form.feedback.message}
                        context={{ operation: "mutation", outcome: "rejected" }}
                        className={cn(styles.status, "error")}
                        compact
                      />
                    )}
                  </div>
                </div>
              </fieldset>
              <div>
                <Button
                  ref={form.submitRef}
                  className={styles.enter}
                  type="submit"
                  disabled={Boolean(form.pending)}
                  loading={form.pending === "password" || form.pending === "guest"}
                >
                  <span>
                    {form.pending === "guest"
                      ? "正在进入…"
                      : form.pending === "password"
                        ? "正在登录…"
                        : "登录"}
                  </span>
                  <ArrowUpRight aria-hidden="true" />
                </Button>
                <div className={styles["other-signin"]} aria-labelledby="other-signin-title">
                  <div className={styles["other-signin-label"]} id="other-signin-title">
                    其他登录方式
                  </div>
                  <div className={styles["other-signin-options"]}>
                    <Button
                      className={styles.github}
                      variant="outline"
                      size="icon"
                      type="button"
                      aria-label={
                        form.pending === "github" ? "正在前往 GitHub…" : "使用 GitHub 登录"
                      }
                      title={form.githubEnabled ? "使用 GitHub 登录" : "GitHub 登录暂不可用"}
                      loading={form.pending === "github"}
                      disabled={Boolean(form.pending) || !form.githubEnabled}
                      onClick={() => {
                        void form.enter("github");
                      }}
                    >
                      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                        <path d="M12 .297C5.37.297 0 5.67 0 12.297c0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.043-1.61-4.043-1.61-.546-1.387-1.333-1.756-1.333-1.756-1.09-.745.084-.729.084-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.835 2.809 1.305 3.495.998.108-.776.418-1.305.762-1.605-2.665-.3-5.467-1.334-5.467-5.93 0-1.31.469-2.381 1.236-3.221-.124-.303-.536-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.655 1.652.243 2.873.12 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.625-5.479 5.921.43.372.823 1.102.823 2.222 0 1.606-.015 2.898-.015 3.293 0 .319.216.694.825.576C20.565 22.092 24 17.592 24 12.297 24 5.67 18.627.297 12 .297z" />
                      </svg>
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      type="button"
                      title="以游客身份浏览"
                      disabled={Boolean(form.pending)}
                      onClick={() => {
                        void form.enter("guest");
                      }}
                    >
                      随便看看
                      <ArrowRight aria-hidden="true" />
                    </Button>
                  </div>
                </div>
              </div>
            </Form>
          </div>

          <div className={styles["caption"]}>NiumaCrew · 让工作轻一点。</div>
          <div className={styles["brand-stage"]} data-signin-stage>
            <div
              className={styles["perch"]}
              data-signin-perch
              dangerouslySetInnerHTML={{ __html: signinLogo }}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
export { SigninPage as Component };
