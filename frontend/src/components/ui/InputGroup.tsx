// Adapted from shadcn/ui (MIT). See THIRD_PARTY_NOTICES.md.
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";

function InputGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="input-group"
      role="group"
      className={cn(
        "group/input-group relative flex w-full min-w-0 flex-col items-center rounded-card [corner-shape:round] border border-input bg-surface p-2 shadow-composer outline-none transition-[border-color,box-shadow] focus-within:border-field-focus focus-within:ring-[3px] focus-within:ring-field-focus/50 has-[[aria-invalid=true]]:border-danger has-[[aria-invalid=true]]:focus-within:ring-danger/20 has-[>textarea]:h-auto",
        className,
      )}
      {...props}
    />
  );
}

const inputGroupAddonVariants = cva(
  "flex cursor-text items-center justify-center gap-2 px-1 py-1 select-none",
  {
    variants: {
      align: {
        "inline-start": "order-first",
        "inline-end": "order-last",
        "block-start": "order-first w-full justify-start",
        "block-end": "order-last w-full justify-start",
      },
    },
    defaultVariants: {
      align: "inline-start",
    },
  },
);

function InputGroupAddon({
  className,
  align = "inline-start",
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof inputGroupAddonVariants>) {
  return (
    <div
      role="group"
      data-slot="input-group-addon"
      data-align={align}
      className={cn(inputGroupAddonVariants({ align }), className)}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest("button")) {
          return;
        }
        e.currentTarget.parentElement
          ?.querySelector<HTMLInputElement | HTMLTextAreaElement>("input,textarea")
          ?.focus();
      }}
      {...props}
    />
  );
}

const inputGroupButtonVariants = cva("flex items-center shadow-none", {
  variants: {
    size: {
      xs: "",
      sm: "",
      "icon-xs": "",
      "icon-sm": "",
    },
  },
  defaultVariants: {
    size: "xs",
  },
});

function InputGroupButton({
  className,
  type = "button",
  variant = "ghost",
  size = "xs",
  ...props
}: Omit<React.ComponentProps<typeof Button>, "size" | "type"> &
  VariantProps<typeof inputGroupButtonVariants> & {
    type?: "button" | "submit" | "reset";
  }) {
  return (
    <Button
      type={type}
      size={size}
      variant={variant}
      className={cn(inputGroupButtonVariants({ size }), className)}
      {...props}
    />
  );
}

function InputGroupText({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span className={cn("flex items-center [&_svg]:pointer-events-none", className)} {...props} />
  );
}

function InputGroupInput({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <Input
      data-slot="input-group-control"
      className={cn(
        "flex-1 border-0 bg-transparent shadow-none focus:ring-0 aria-invalid:focus:ring-0",
        className,
      )}
      {...props}
    />
  );
}

function InputGroupTextarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <Textarea
      data-slot="input-group-control"
      className={cn(
        "min-h-20 max-h-60 flex-1 resize-none rounded-none border-0 bg-transparent px-2 py-2 shadow-none focus:ring-0 aria-invalid:focus:ring-0",
        className,
      )}
      {...props}
    />
  );
}

export {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupText,
  InputGroupInput,
  InputGroupTextarea,
};
