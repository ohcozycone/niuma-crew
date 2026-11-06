import { ArrowUpRight, Plus, RefreshCw, Save, Settings2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ButtonGroup } from "@/components/ui/ButtonGroup";
import { Card } from "@/components/ui/Card";
import { styles } from "./previewStyles";

export function ButtonExamples({ notify }: { notify: (message: string) => void }) {
  return (
    <Card as="section" variant="outline" radius="panel" className={styles.panel} id="buttons">
      <div className={styles.panelTitle}>
        <h3 className="mb-4 font-semibold">按钮与操作</h3>
        <span>主操作明确，辅助操作柔和；常态、悬停与选中各有层级</span>
      </div>
      <div className="grid gap-x-10 gap-y-5 md:grid-cols-2">
        <div className="flex items-center gap-4">
          <Button onClick={() => notify("主操作样板：创建员工")}>
            <Plus />
            创建员工
          </Button>
          <p className="type-caption">主操作 · 创建、提交、保存</p>
        </div>
        <div className="flex items-center gap-4">
          <Button variant="secondary" onClick={() => notify("次级强调样板：去对话")}>
            去对话
            <ArrowUpRight />
          </Button>
          <p className="type-caption">次级强调 · 重复出现的继续入口</p>
        </div>
        <div className="flex items-center gap-4">
          <Button variant="outline" onClick={() => notify("次操作样板：配置能力")}>
            <Settings2 />
            配置能力
          </Button>
          <p className="type-caption">次操作 · 配置、取消、返回</p>
        </div>
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => notify("轻操作样板：执行日志")}>
            执行日志
          </Button>
          <p className="type-caption">轻操作 · 查看、刷新、行内辅助</p>
        </div>
        <div className="flex items-center gap-4">
          <Button variant="destructive-ghost" onClick={() => notify("危险入口样板，未删除数据")}>
            <Trash2 />
            删除员工
          </Button>
          <p className="type-caption">危险入口 · 打开确认步骤</p>
        </div>
        <div className="flex items-center gap-4">
          <Button variant="destructive" onClick={() => notify("最终确认样板，未删除数据")}>
            确认删除
          </Button>
          <p className="type-caption">危险确认 · 执行删除或放弃修改</p>
        </div>
      </div>
      <p className="type-caption mt-5">
        无底按钮悬停使用浅暖灰底，文字略微加深；导航选中使用更深一级暖灰，离开鼠标后仍保留。陶色留给继续入口和已选筛选，危险操作保留红色提示。
      </p>
      <div className="mt-6 border-t border-border pt-5">
        <h4 className="mb-3 text-sm font-medium">尺寸与状态</h4>
        <ButtonGroup align="start">
          <Button size="xs" variant="outline" onClick={() => notify("紧凑尺寸样板")}>
            紧凑
          </Button>
          <Button size="sm" variant="outline" onClick={() => notify("行内尺寸样板")}>
            行内操作
          </Button>
          <Button variant="outline" onClick={() => notify("标准尺寸样板")}>
            标准操作
          </Button>
          <Button size="lg" onClick={() => notify("重要入口样板")}>
            重要入口
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="刷新样板"
            onClick={() => notify("刷新样板")}
          >
            <RefreshCw />
          </Button>
          <Button disabled>暂不可用</Button>
          <Button loading>
            <Save />
            保存中…
          </Button>
          <Button variant="secondary" loading>
            打开中…
          </Button>
        </ButtonGroup>
        <p className={`${styles.caption} mt-3`}>
          统一 8px 圆角，图标通常为 16px；触屏目标至少
          44px。可用次操作保留描边；禁用取消描边、文字减弱。加载保留动作颜色，键盘焦点使用主题外圈。
        </p>
      </div>
      <div className="mt-6 border-t border-border pt-5">
        <h4 className="mb-3 text-sm font-medium">实际组合</h4>
        <div className="flex flex-wrap items-center justify-between gap-4 py-3">
          <span className="type-caption">编辑页</span>
          <div className="flex min-w-0 flex-col items-end gap-1">
            <div className="flex flex-wrap items-center gap-6 max-sm:gap-3">
              <Button variant="destructive-ghost" onClick={() => notify("危险入口与保存操作分组")}>
                删除员工
              </Button>
              <ButtonGroup role="group" aria-label="编辑页操作样板">
                <Button variant="outline" onClick={() => notify("返回样板")}>
                  返回
                </Button>
                <Button disabled>
                  <Save />
                  保存配置
                </Button>
              </ButtonGroup>
            </div>
            <p className="type-caption min-h-4.5">已保存</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border py-3">
          <span className="type-caption">列表工具栏</span>
          <ButtonGroup role="group" aria-label="列表操作样板">
            <Button
              variant="ghost"
              size="icon"
              aria-label="刷新列表样板"
              onClick={() => notify("刷新列表样板")}
            >
              <RefreshCw />
            </Button>
            <Button onClick={() => notify("新对话样板")}>
              <Plus />
              新对话
            </Button>
          </ButtonGroup>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border py-3">
          <span className="type-caption">危险确认弹窗</span>
          <ButtonGroup role="group" aria-label="危险确认样板">
            <Button variant="outline" onClick={() => notify("取消样板")}>
              取消
            </Button>
            <Button variant="destructive" onClick={() => notify("危险确认样板，未删除数据")}>
              确认删除
            </Button>
          </ButtonGroup>
        </div>
        <p className={`${styles.caption} mt-3`}>
          同一组只保留一个实心操作；陶色用于继续入口和选中，不与主操作并列争夺注意力。危险确认独立成组，两主题沿用相同顺序，窄屏按内容换行。
        </p>
      </div>
    </Card>
  );
}
