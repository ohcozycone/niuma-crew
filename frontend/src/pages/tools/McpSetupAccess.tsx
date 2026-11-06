import { FormField } from "@/components/common/FormField";
import { SelectField } from "@/components/ui/SelectField";
import { Input } from "@/components/ui/Input";
import type { McpInputField } from "@/lib/api/tools";

import { OAuthConfigurationFields, type OAuthFieldsValue } from "./OAuthConfigurationFields";

export function McpSetupAccess({
  transport,
  fields,
  keys,
  scope,
  onScope,
  auth,
  onAuth,
  header,
  onHeader,
  token,
  onToken,
  oauth,
  onOAuth,
  environment,
  onEnvironment,
}: {
  transport: "http" | "stdio";
  fields: McpInputField[];
  keys: string[];
  scope: string;
  onScope: (value: string) => void;
  auth: string;
  onAuth: (value: string) => void;
  header: string;
  onHeader: (value: string) => void;
  token: string;
  oauth?: OAuthFieldsValue;
  onOAuth?: (value: OAuthFieldsValue) => void;
  onToken: (value: string) => void;
  environment: Record<string, string>;
  onEnvironment: (value: Record<string, string>) => void;
}) {
  return (
    <section className="space-y-4 border-t border-border pt-5">
      <h2 className="type-title">访问设置</h2>
      <p className="type-caption">
        选择浏览器授权或填写自己的密钥。描述中标为可选的字段可以留空；连接后仍需到员工页面主动装配。
      </p>
      <div className="form-grid">
        <FormField label={<>使用范围</>}>
          <SelectField
            value={scope}
            onValueChange={(nextValue) => onScope(nextValue)}
            options={[
              { value: "personal", label: "个人账号（仅本人使用）" },
              { value: "shared", label: "明确共用账号" },
            ]}
          />
        </FormField>
        <FormField label={<>认证方式</>}>
          <SelectField
            value={auth}
            onValueChange={(nextValue) => onAuth(nextValue)}
            options={[
              {
                value: "none",
                label: "不提供密钥（匿名访问）",
                disabled: fields.some((field) => field.is_required),
              },
              ...(transport === "stdio"
                ? [{ value: "env", label: "环境变量（API Key 等）", disabled: !keys.length }]
                : [
                    { value: "bearer", label: "Bearer Token" },
                    { value: "header", label: "自定义认证头" },
                    { value: "oauth", label: "OAuth（浏览器授权）" },
                  ]),
            ]}
          />
        </FormField>
      </div>
      {transport === "stdio" &&
        auth === "env" &&
        keys.map((key) => {
          const field = fields.find((item) => item.name === key);
          return (
            <FormField
              key={key}
              description={field?.description}
              label={
                <>
                  {key}
                  {field && !field.is_required ? "（可选）" : ""}
                </>
              }
            >
              <Input
                required={field?.is_required ?? true}
                type={field?.is_secret === false ? "text" : "password"}
                autoComplete="off"
                value={environment[key] ?? ""}
                onChange={(e) => onEnvironment({ ...environment, [key]: e.target.value })}
              />
            </FormField>
          );
        })}
      {transport === "http" && auth === "oauth" && oauth && onOAuth && (
        <OAuthConfigurationFields value={oauth} onChange={onOAuth} />
      )}
      {transport === "http" && auth === "header" && (
        <FormField label={<>认证头名称</>}>
          <Input required value={header} onChange={(e) => onHeader(e.target.value)} />
        </FormField>
      )}
      {transport === "http" && auth !== "none" && auth !== "oauth" && (
        <FormField
          description={fields[0]?.description}
          label={
            <>
              API Key / Token
              {fields.length > 0 && fields.every((field) => !field.is_required) ? "（可选）" : ""}
            </>
          }
        >
          <Input
            type="password"
            autoComplete="off"
            required={!fields.length || fields.some((field) => field.is_required)}
            value={token}
            onChange={(e) => onToken(e.target.value)}
            maxLength={4096}
          />
        </FormField>
      )}
    </section>
  );
}
