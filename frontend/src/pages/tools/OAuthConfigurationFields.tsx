import { FormField } from "@/components/common/FormField";
import { Input } from "@/components/ui/Input";

export type OAuthFieldsValue = { scopes: string; clientId: string; clientSecret: string };
export const emptyOAuthFields: OAuthFieldsValue = { scopes: "", clientId: "", clientSecret: "" };
export function oauthPublicConfig(value: OAuthFieldsValue) {
  return {
    scopes: value.scopes.split(/\s+/).filter(Boolean),
    ...(value.clientId.trim() ? { client_id: value.clientId.trim() } : {}),
  };
}
export function OAuthConfigurationFields({
  value,
  onChange,
}: {
  value: OAuthFieldsValue;
  onChange: (value: OAuthFieldsValue) => void;
}) {
  return (
    <details className="col-span-full">
      <summary className="cursor-pointer type-caption">高级授权设置（通常无需填写）</summary>
      <div className="form-grid mt-4">
        <FormField label="权限 scopes" description="留空由服务提供默认权限；多个值用空格分隔。">
          <Input
            value={value.scopes}
            onChange={(event) => onChange({ ...value, scopes: event.target.value })}
          />
        </FormField>
        <FormField label="Client ID" description="仅服务要求预注册应用时填写。">
          <Input
            value={value.clientId}
            onChange={(event) => onChange({ ...value, clientId: event.target.value })}
          />
        </FormField>
        <FormField label="Client Secret" description="仅预注册应用需要；留空保留已有值。">
          <Input
            type="password"
            autoComplete="off"
            value={value.clientSecret}
            onChange={(event) => onChange({ ...value, clientSecret: event.target.value })}
          />
        </FormField>
      </div>
    </details>
  );
}
