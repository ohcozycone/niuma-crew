import { FormField } from "@/components/common/FormField";
import { AccountMenuButton } from "@/components/auth/AccountMenuButton";
import { NavigationItem } from "@/components/ui/NavigationItem";
import { Card } from "@/components/ui/Card";
import { useState } from "react";
import { LogOut, Plus, Users } from "lucide-react";
import { ResourceIcon } from "@/components/common/ResourceIcon";
import { Button } from "@/components/ui/Button";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/Pagination";
import { TabsContent } from "@/components/ui/Tabs";
import { PageTabs } from "@/components/common/PageTabs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { PageHeading } from "@/components/common/PageHeading";
import { PageBreadcrumb } from "@/components/common/PageBreadcrumb";
import { FavoriteAgentLink } from "@/components/navigation/FavoriteAgentLink";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Switch } from "@/components/ui/Switch";
import { SelectField } from "@/components/ui/SelectField";
import { contrastExceptions, agentNavigationRoles } from "@/design-system/spec";
import { useTheme } from "@/state/theme/useTheme";
import { useThemeValues } from "./useThemeValues";
import { styles } from "./previewStyles";
import { ButtonExamples } from "./ButtonExamples";
const navigationAgents = [
  { avatarId: "programmer", name: "架构师老登" },
  { avatarId: "admin", name: "行政管家小 K" },
  { avatarId: "finance", name: "财务管家" },
  { avatarId: "designer", name: "设计搭档" },
  { avatarId: "product", name: "产品经理" },
  { avatarId: "sysadmin", name: "运维管家 · 基础设施与服务稳定性支持" },
];
export function ComponentExamples({ notify: setNotice }: { notify: (message: string) => void }) {
  const { resolved } = useTheme();
  const { number } = useThemeValues();
  const [navigationSample, setNavigationSample] = useState("agents");
  const [exampleState, setExampleState] = useState("available");
  const [samplePage, setSamplePage] = useState(1);
  const [sampleEnabled, setSampleEnabled] = useState(true);
  return (
    <div className={"space-y-5"}>
      {" "}
      <Card as="div" variant="outline" radius="panel" className={styles.panel}>
        <div className={styles.panelTitle}>
          <h3 className={"mb-4 font-semibold"}>导航与图标状态</h3>
          <span>使用工作台同一份菜单样式，点击切换当前态</span>
        </div>
        <nav className={styles.navPreview} aria-label="菜单状态样板">
          <NavigationItem
            active={navigationSample === "agents"}
            type="button"

            aria-pressed={navigationSample === "agents"}
            onClick={() => setNavigationSample("agents")}
          >
            <Users aria-hidden="true" />
            <span>数字员工</span>
            <small>6</small>
          </NavigationItem>
          <NavigationItem
            active={navigationSample === "skills"}
            type="button"

            aria-pressed={navigationSample === "skills"}
            onClick={() => setNavigationSample("skills")}
          >
            <ResourceIcon kind="capabilities" />
            <span>能力库</span>
            <small>12</small>
          </NavigationItem>
        </nav>
        <p className={styles.caption}>
          已选项在悬停时保持当前颜色，其他项悬停显示浅灰底。图标 {number("--os-nav-icon-size")}
          px，描边常态 {number("--os-nav-icon-stroke")}
          px、当前 {number("--os-nav-icon-active-stroke")}
          px；当前项暖灰底，文字、图标与数量共用 nav-active-text，文字与数量为{" "}
          {number("--os-nav-active-weight")} 字重，数量去底框。
        </p>
        {contrastExceptions
          .filter((exception) => exception.mode === resolved)
          .map((exception) => (
            <p key={exception.foreground} className={styles.caption}>
              {exception.reason}
            </p>
          ))}
      </Card>
      <Card as="div" variant="outline" radius="panel" className={styles.panel}>
        <div className={styles.panelTitle}>
          <h3 className="mb-4 font-semibold">面包屑导航</h3>
          <span>模块入口与当前员工</span>
        </div>
        <PageBreadcrumb parent={{ label: "数字员工", to: "/agents" }} current="架构师老赵" />
        <p className={styles.caption}>
          外壳和对话页共用同一组件，父级可返回所属列表，当前项只显示文字。对话页在面包屑后紧接问题图标与内容。
        </p>
      </Card>
      <Card
        as="div"
        variant="outline"
        radius="panel"
        className={styles.panel}
        id="account-navigation"
      >
        <div className={styles.panelTitle}>
          <h3 className={"mb-4 font-semibold"}>底部账户入口</h3>
          <span>紧凑双行身份，向上展开退出菜单</span>
        </div>
        <div className={styles.accountPreview}>
          <DropdownMenu modal={false}>
            <DropdownMenuTrigger
              render={
                <AccountMenuButton
                  username="admin"
                  roleLabel="平台管理员"
                  aria-label="账户菜单样板"
                />
              }
            />
            <DropdownMenuContent side="top" align="start">
              <DropdownMenuItem
                tone="destructive"
                onClick={() => setNotice("账户菜单样板：正式页面在这里退出登录。")}
              >
                <LogOut aria-hidden="true" />
                退出登录
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <p className={styles.caption}>
          28px 头像与双行文字合为 48px 整行入口；正式侧栏只滚动收藏列表，滚动停止后隐藏滑块，600px
          以下高度切换为整体滚动。Enter 展开菜单，Escape 关闭并返回焦点。
        </p>
      </Card>
      <Card
        as="div"
        variant="outline"
        radius="panel"
        className={styles.panel}
        id="agent-navigation"
      >
        <div className={styles.panelTitle}>
          <h3 className={"mb-4 font-semibold"}>收藏员工导航</h3>
          <span>主区域进入员工主页，右侧新建对话</span>
        </div>
        <div className={styles.foundationGrid}>
          <nav
            className={`${styles.navPreview} flex flex-col flex-1 [gap:var(--os-favorite-stack)] min-w-0 min-h-0 [margin:-4px] p-1 overflow-y-auto [overscroll-behavior:contain] [scrollbar-gutter:stable] [scrollbar-width:thin] [scrollbar-color:transparent_transparent] [@supports_selector(::-webkit-scrollbar)]:[scrollbar-width:auto] [@supports_selector(::-webkit-scrollbar)]:[scrollbar-color:auto] [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:[background:transparent] [&::-webkit-scrollbar-thumb]:rounded-control [&::-webkit-scrollbar-thumb]:[background:transparent] [@supports_not_selector(::-webkit-scrollbar)]:[&[data-scrolling]]:[scrollbar-color:var(--os-text-muted)_transparent] [&[data-scrolling]::-webkit-scrollbar-thumb]:bg-text-muted [&_>_p]:m-0 [&_>_p]:text-text-muted [&_>_p]:[font-size:var(--os-text-caption)] [&_>_p]:[padding:12px_8px] [@media(max-height:_600px)]:[flex:0_0_auto] [@media(max-height:_600px)]:overflow-visible [@media(max-height:_600px)]:[scrollbar-gutter:auto]`}
            aria-label="收藏员工导航样板"
          >
            {navigationAgents.map((agent) => (
              <FavoriteAgentLink
                key={agent.avatarId}
                name={agent.name}
                avatarId={agent.avatarId}
                to="/agents"
                label={`查看${agent.name}的导航样板`}
                conversationTo="/agents"
              />
            ))}
          </nav>
          <div>
            <dl className={styles.navigationTokens}>
              {Object.entries(agentNavigationRoles).map(([key, label]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{number(`--os-${key}`)}px</dd>
                </div>
              ))}
            </dl>
            <p className={styles.caption}>
              正式侧栏主区域进入员工主页，右侧悬停或聚焦显示新建对话入口；触屏常驻。
              对话入口固定预留，分隔处点击不跳转，两个入口各有焦点轮廓。本样板主入口前往员工列表，
              对话入口前往员工列表选择员工。六角色共用完整 SVG，长名称省略，头像保持尺寸。
            </p>
          </div>
        </div>
      </Card>
      <Card as="div" variant="outline" radius="panel" className={styles.panel}>
        <div className={styles.panelTitle}>
          <h3 className={"mb-4 font-semibold"}>功能页标题</h3>
          <span>中文标题与局部衬色，说明在下，操作靠右</span>
        </div>
        <PageHeading
          title="数字员工"
          description="为合适的员工配齐能力，交办工作。"
          actions={
            <Button onClick={() => setNotice("已触发创建员工示例")}>
              <Plus />
              创建员工
            </Button>
          }
          headingLevel={2}
        />
        <p className={styles.caption}>
          标题 {number("--os-type-page-size")}px / {number("--os-type-page-weight")}，说明{" "}
          {number("--os-type-description-size")}px； 窄屏标题 {number("--os-type-section-size")}
          px。局部衬色使用 title-accent， 标题到说明 {number("--os-heading-description-gap")}
          px，页头后留 {number("--os-heading-content-gap")}px。 所有功能页使用相同的中文标题组合。
        </p>
        <details className={styles.headingVariants}>
          <summary>长标题与数量布局样板</summary>
          <PageHeading
            title="项目知识与员工能力配置管理"
            description="为团队选择合适的数字员工，配置可复用的技能，并查看已有的知识与能力配置。较长的说明允许完整换行。"
            meta="128 项能力"
            headingLevel={2}
          />
          <PageHeading
            title="模型连接"
            description="统一管理团队使用的模型连接。"
            meta="3 个连接"
            actions={<Button onClick={() => setNotice("已触发连接示例")}>添加连接</Button>}
            headingLevel={2}
          />
        </details>
      </Card>
      <Card as="div" variant="outline" radius="panel" className={styles.panel}>
        <div className={styles.panelTitle}>
          <h3 className={"mb-4 font-semibold"}>Tab 滑动指示线</h3>
          <span>首次直接定位，切换时同步移动和伸缩</span>
        </div>
        <PageTabs
          defaultValue="favorites"
          label="Tab 动效样板"
          trailing="128 位员工"
          items={[
            { value: "all", label: "全部员工", count: 128 },
            { value: "favorites", label: "已收藏" },
            { value: "paused", label: "已暂停" },
          ]}
        >
          <TabsContent value="all">全部员工示例</TabsContent>
          <TabsContent value="favorites">已收藏员工示例</TabsContent>
          <TabsContent value="paused">已暂停员工示例</TabsContent>
        </PageTabs>
        <p className={styles.caption}>
          默认选中中间项；可连续点击或用方向键切换。右侧槽位承载数量、状态或操作，空间不足时换行。
          选中项在悬停时保持外观；线条匹配包含数量的 Tab 宽度，减少动态效果时直接切换。
        </p>
      </Card>
      <Card as="div" variant="outline" radius="panel" className={styles.panel} id="pagination">
        <div className={styles.panelTitle}>
          <h3 className="mb-4 font-semibold">分页</h3>
          <span>纯箭头翻页，当前页使用轮廓选中态</span>
        </div>
        <Pagination aria-label="分页样板">
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                disabled={samplePage === 1}
                onClick={() => setSamplePage(samplePage - 1)}
              />
            </PaginationItem>
            {[1, 2, 3].map((page) => (
              <PaginationItem key={page}>
                <PaginationLink
                  aria-label={`第 ${page} 页`}
                  isActive={samplePage === page}
                  onClick={() => setSamplePage(page)}
                >
                  {page}
                </PaginationLink>
              </PaginationItem>
            ))}
            <PaginationItem>
              <PaginationNext
                disabled={samplePage === 3}
                onClick={() => setSamplePage(samplePage + 1)}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
        <p className={styles.caption}>
          与员工目录共用组件；此处为三页演示数据，不请求业务接口。Tab 聚焦后可用 Enter
          或空格翻页，首尾箭头禁用。
        </p>
      </Card>
      <ButtonExamples notify={setNotice} />
      <div className={styles.foundationGrid}>
        <Card as="div" variant="outline" radius="panel" className={styles.panel}>
          <h3 className={"mb-4 font-semibold"}>输入与说明</h3>
          <FormField className="mb-4" label="员工名称" description="标签常驻，占位符提供填写示例。">
            <Input placeholder="例如：行政管家" maxLength={80} />
          </FormField>
          <FormField className="mb-4" label={<>职责描述</>}>
            <Textarea placeholder="描述员工可以协助处理的工作…" rows={3} />
          </FormField>
          <p className={styles.caption}>
            沿用 shadcn 的普通圆角与中性灰焦点外圈；输入框、文本域和搜索框遵循同一规范。
          </p>
        </Card>
        <Card as="div" variant="outline" radius="panel" className={styles.panel}>
          <h3 className={"mb-4 font-semibold"}>选择与校验</h3>
          <FormField className="mb-4" htmlFor="sample-status" label="员工状态">
            <SelectField
              options={[
                { value: "available", label: "可对话" },
                { value: "paused", label: "已暂停" },
                { value: "unconfigured", label: "待配置模型" },
              ]}
              value={exampleState}
              onValueChange={setExampleState}
              icon={<Users size={16} />}
              id="sample-status"
              className="w-fit"
            />
          </FormField>
          <FormField className="mb-4" label="必填字段" error="请填写员工名称">
            <Input placeholder="请输入员工名称" />
          </FormField>
          <div className={styles.switchLine}>
            <label htmlFor="sample-switch">启用员工示例</label>
            <Switch id="sample-switch" checked={sampleEnabled} onCheckedChange={setSampleEnabled} />
          </div>
          <p className={styles.caption}>
            选择项可用方向键切换；图标、选项和禁用状态统一通过 SelectField
            配置。错误直接显示在字段旁，并与输入关联。
          </p>
        </Card>
      </div>
    </div>
  );
}
