import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
export function StaleDraftNotice({
  visible,
  onRestore,
  onDiscard,
}: {
  visible: boolean;
  onRestore: () => void;
  onDiscard: () => void;
}) {
  if (!visible) return null;
  return (
    <Card
      as="div"
      variant="outline"
      radius="panel"
      role="status"
      className="mb-4 p-4 text-sm space-y-3"
    >
      <p>服务器配置已更新，旧修订草稿仍保留在当前标签页。先恢复或丢弃，再继续编辑。</p>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={onRestore}>
          恢复旧草稿
        </Button>
        <Button type="button" variant="ghost" onClick={onDiscard}>
          丢弃旧草稿
        </Button>
      </div>
    </Card>
  );
}
