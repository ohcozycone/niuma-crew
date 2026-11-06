import { AgentAvatar } from "./AgentAvatar";
import { Check } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { defaultAvatarId, agentAvatars, findAvatar } from "../../lib/avatars/registry";

export function AvatarPicker({
  value,
  onSelect,
  onClose,
}: {
  value: string;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const selectedId = findAvatar(value)?.id ?? defaultAvatarId;
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="wide" className={"flex flex-col gap-4"}>
        <DialogHeader>
          <DialogTitle>选择头像</DialogTitle>
          <DialogDescription>
            从已有的 {agentAvatars.length} 个头像中选择，随时可以更换。
          </DialogDescription>
        </DialogHeader>
        <div
          className={
            "grid [grid-template-columns:repeat(5,_minmax(0,_1fr))] gap-2.5 overflow-y-auto min-h-0 p-[3px] [overscroll-behavior:contain] [&_>_button]:min-w-0 [&_>_button]:[aspect-ratio:1] [&_>_button]:[border:1px_solid_var(--os-border)] [&_>_button]:rounded-panel [&_>_button]:bg-surface [&_>_button]:p-2.5 [&_>_button]:flex [&_>_button]:items-center [&_>_button]:justify-center [&_>_button]:flex-col [&_>_button]:relative [&_>_button:hover]:bg-muted [&_>_button:hover]:border-focus [&_>_button[aria-pressed='true']]:bg-muted [&_>_button[aria-pressed='true']]:border-focus max-[600px]:[grid-template-columns:repeat(3,_minmax(0,_1fr))] max-[600px]:gap-2"
          }
          aria-label="可选头像"
        >
          {agentAvatars.map((avatar, index) => (
            <button
              type="button"
              key={avatar.id}
              aria-pressed={selectedId === avatar.id}
              aria-label={`头像 ${index + 1}`}
              onClick={() => onSelect(avatar.id)}
            >
              <span
                className={
                  "flex w-21.5 max-w-full [aspect-ratio:1] items-center justify-center [&_svg]:w-full [&_svg]:h-full [&_svg]:object-contain max-[600px]:w-19"
                }
              >
                <AgentAvatar avatarId={avatar.id} size="100%" />
              </span>
              {selectedId === avatar.id && (
                <span
                  className={
                    "absolute top-1.5 right-1.5 rounded-full bg-action text-surface w-4.5 h-4.5 grid [place-items:center]"
                  }
                >
                  <Check size={12} />
                </span>
              )}
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
