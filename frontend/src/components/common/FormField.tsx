import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  type ComponentPropsWithRef,
  type ReactElement,
  type ReactNode,
} from "react";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { SelectField } from "@/components/ui/SelectField";
import { Field, FieldLabel, FieldDescription, FieldError } from "@/components/ui/Field";
type ControlProps = {
  id?: string;
  children?: ReactNode;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean | "true" | "false" | "grammar" | "spelling";
};
const controls: unknown[] = [Input, Textarea, SelectField, "input", "textarea"];
function firstControl(nodes: ReactNode): ReactElement<ControlProps> | undefined {
  for (const node of Children.toArray(nodes)) {
    if (!isValidElement<ControlProps>(node)) continue;
    if (controls.includes(node.type)) return node;
    const nested = firstControl(node.props.children);
    if (nested) return nested;
  }
}
type Props = ComponentPropsWithRef<"div"> & {
  label: ReactNode;
  htmlFor?: string;
  description?: ReactNode;
  error?: ReactNode;
};
/** One ordinary field: its label, control association, helper text and error stay together. */
export function FormField({
  label,
  htmlFor,
  description,
  error,
  children,
  className,
  ...props
}: Props) {
  const generated = useId();
  const controlId = htmlFor ?? firstControl(children)?.props.id ?? generated;
  let attached = false;
  function attach(nodes: ReactNode): ReactNode {
    return Children.map(nodes, (node) => {
      if (!isValidElement<ControlProps>(node)) return node;
      if (!attached && controls.includes(node.type)) {
        attached = true;
        const described =
          [
            node.props["aria-describedby"],
            description ? `${generated}-help` : null,
            error ? `${generated}-error` : null,
          ]
            .filter(Boolean)
            .join(" ") || undefined;
        return cloneElement(node, {
          id: controlId,
          "aria-describedby": described,
          "aria-invalid": error ? true : node.props["aria-invalid"],
        });
      }
      return node.props.children
        ? cloneElement(node, { children: attach(node.props.children) })
        : node;
    });
  }
  return (
    <Field
      data-slot="form-field"
      invalid={error ? true : undefined}
      className={className}
      {...props}
    >
      <FieldLabel htmlFor={controlId}>{label}</FieldLabel>
      {attach(children)}
      {description && <FieldDescription id={`${generated}-help`}>{description}</FieldDescription>}
      {error && (
        <FieldError id={`${generated}-error`} role="alert" match>
          {error}
        </FieldError>
      )}
    </Field>
  );
}
