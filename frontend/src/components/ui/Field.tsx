// Field composition follows shadcn/ui (MIT); Base UI owns field semantics.
import { Field as Primitive } from "@base-ui/react/field";
import { cn } from "@/lib/utils";
import type { StyledProps } from "./styledProps";

function Field({ className, ...props }: StyledProps<Primitive.Root.Props>) {
  return (
    <Primitive.Root
      data-slot="field"
      className={cn("grid min-w-0 gap-2 text-sm", className)}
      {...props}
    />
  );
}
function FieldLabel({ className, ...props }: StyledProps<Primitive.Label.Props>) {
  return (
    <Primitive.Label data-slot="field-label" className={cn("font-medium", className)} {...props} />
  );
}
const FieldControl = Primitive.Control;
function FieldDescription({ className, ...props }: StyledProps<Primitive.Description.Props>) {
  return (
    <Primitive.Description
      data-slot="field-description"
      className={cn("-mt-1 text-xs leading-relaxed text-text-muted", className)}
      {...props}
    />
  );
}
function FieldError({ className, ...props }: StyledProps<Primitive.Error.Props>) {
  return (
    <Primitive.Error
      data-slot="field-error"
      className={cn("-mt-1 text-xs leading-relaxed text-danger", className)}
      {...props}
    />
  );
}
export { Field, FieldLabel, FieldControl, FieldDescription, FieldError };
