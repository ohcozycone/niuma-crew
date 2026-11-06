import { resourceIdentity } from "@/components/common/ResourceIcon";
import { FailureNotice } from "@/components/failure/FailureNotice";
import { NavigationItem } from "@/components/ui/NavigationItem";
import { GlobalSearch } from "@/components/navigation/GlobalSearch";
import { SearchInput } from "@/components/common/SearchInput";
import { PageToolbarProvider, PageToolbarTarget } from "@/components/common/PageToolbar";
import { PageBreadcrumb } from "@/components/common/PageBreadcrumb";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Outlet, useBlocker, useLocation, useNavigate, useNavigation } from "react-router";
import { Menu, Search, X } from "lucide-react";
import { AuthBoundary } from "@/components/auth/AuthBoundary";
import { useIdentity } from "@/state/auth/useIdentity";
import { AccountMenu } from "@/components/auth/AccountMenu";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { FavoriteAgentLink } from "@/components/navigation/FavoriteAgentLink";
import { Button } from "@/components/ui/Button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/Tooltip";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { WorkspaceDataProvider } from "@/state/workspace/WorkspaceDataProvider";
import { useNavigationSummary } from "@/components/navigation/useNavigationSummary";
import { EditingProvider, useEditing } from "@/state/editing/useEditing";
import { identityKey } from "@/lib/identity";
import { returnPath, sourceLink } from "@/lib/navigation";
import { isRulesLocation, leavesEditingArea } from "@/lib/navigation";
import { brand } from "@/lib/brand";
import { ThemeSwitcher } from "@/components/theme/ThemeSwitcher";
import { KnowledgeUploadPanel } from "@/components/knowledge/KnowledgeUploadPanel";
import { useWorkspaceData } from "@/state/workspace/useWorkspaceData";
const navigation = [
  { path: "/agents", title: "数字员工", help: "agents", icon: resourceIdentity.employees.icon },
  { path: "/skills", title: "能力库", help: "skills", icon: resourceIdentity.capabilities.icon },
  { path: "/brains", title: "大脑配置", help: "brains", icon: resourceIdentity.brain.icon },
  {
    path: "/conversations",
    title: "对话记录",
    help: "history",
    icon: resourceIdentity.conversation.icon,
  },
  { path: "/knowledge", title: "知识库", help: "knowledge", icon: resourceIdentity.knowledge.icon },
  { path: "/rules", title: "全员规范", help: "knowledge", icon: resourceIdentity.rules.icon },
];

export function Layout() {
  return (
    <AuthBoundary>
      <WorkspaceDataProvider>
        <PageToolbarProvider>
          <EditingProvider>
            <Shell />
          </EditingProvider>
        </PageToolbarProvider>
      </WorkspaceDataProvider>
    </AuthBoundary>
  );
}

function useScrollActivity<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    let timeout: number | undefined;
    const onScroll = () => {
      element.dataset.scrolling = "true";
      window.clearTimeout(timeout);
      timeout = window.setTimeout(() => {
        delete element.dataset.scrolling;
      }, 700);
    };
    element.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      element.removeEventListener("scroll", onScroll);
      window.clearTimeout(timeout);
      delete element.dataset.scrolling;
    };
  }, []);
  return ref;
}

function Shell() {
  const uploads = useWorkspaceData().knowledge.uploads;
  const identity = useIdentity();
  const data = useNavigationSummary();
  const location = useLocation();
  const navigate = useNavigate();
  const transition = useNavigation();
  const admin = identity.permissions.includes("agents:read");
  const favorites = data.favorites;
  const sidebar = useScrollActivity<HTMLElement>();
  const favoriteList = useScrollActivity<HTMLElement>();
  const [mobile, setMobile] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [search, setSearch] = useState("");
  const editing = useEditing();
  const { dirty, saving, isDirty } = editing;
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      // 保存确认后的导航可能早于外壳重渲染，必须读取编辑器当前状态。
      leavesEditingArea(currentLocation, nextLocation) && (isDirty() || editing.isSaving()),
  );
  useEffect(() => {
    if (blocker.state === "blocked" && !editing.isDirty() && !editing.isSaving()) blocker.proceed();
  }, [blocker, dirty, saving, editing]);
  const main = useRef<HTMLElement>(null);
  const toolPage = location.pathname === "/tools";
  const personalConnections = /^\/agents\/[^/]+\/connections$/.test(location.pathname);
  const current =
    (toolPage
      ? navigation.find((n) => n.path === "/skills")
      : navigation.find((n) => location.pathname.startsWith(n.path))) ?? navigation[0];
  const conversationPage = /^\/conversations\/[^/]+\/?$/.test(location.pathname);
  const parent = conversationPage ? navigation[0] : current;
  const editor = /^\/(agents|skills)\/[^/]+$/.test(location.pathname);
  const nested = location.pathname.replace(/\/+$/, "") !== current.path;
  const creating = location.pathname.endsWith("/new");
  const title = location.pathname.endsWith("/trace")
    ? "执行详情"
    : toolPage
      ? new URLSearchParams(location.search).has("native")
        ? "内置工具"
        : new URLSearchParams(location.search).has("service")
          ? "MCP 配置"
          : "接入 MCP"
      : personalConnections
        ? "我的工具连接"
        : editor
          ? current.path === "/agents"
            ? creating
              ? "创建数字员工"
              : admin
                ? "编辑员工"
                : "员工详情"
            : creating
              ? new URLSearchParams(location.search).get("import") === "1"
                ? "导入 Skill 技能包"
                : "创建技能"
              : "编辑技能"
          : nested && current.path === "/conversations"
            ? creating
              ? "新对话"
              : "对话详情"
            : nested && current.path === "/knowledge"
              ? creating
                ? "新建知识库"
                : location.pathname.includes("/documents/")
                  ? "文档原文"
                  : "库详情"
              : current.title;
  const source = returnPath(new URLSearchParams(location.search), parent.path);
  const parentPath = source.split("?")[0] === parent.path ? source : parent.path;
  const help = editor
    ? "configuration"
    : conversationPage
      ? "chat"
      : isRulesLocation(location)
        ? "rules"
        : current.help;
  const url = location.pathname + location.search;
  useLayoutEffect(() => {
    const target = main.current;
    if (!target) return;
    let saved = 0;
    try {
      saved =
        Number(sessionStorage.getItem(`workspace:scroll:${identityKey(identity)}:${url}`)) || 0;
    } catch {
      /* Optional storage. */
    }
    target.scrollTop = saved;
    setMobile(false);
    setSearchOpen(false);
    const record = () => {
      // Loading content can temporarily clamp the scroll offset before restoration.
      if (saved > 0) return;
      try {
        sessionStorage.setItem(
          `workspace:scroll:${identityKey(identity)}:${url}`,
          String(target.scrollTop),
        );
      } catch {
        /* Optional storage. */
      }
    };
    target.addEventListener("scroll", record, { passive: true });
    window.addEventListener("pagehide", record);
    const observer = new ResizeObserver(() => {
      if (saved > 0) {
        target.scrollTop = saved;
        if (target.scrollTop === saved) saved = 0;
      }
    });
    if (target.firstElementChild) observer.observe(target.firstElementChild);
    return () => {
      target.removeEventListener("scroll", record);
      window.removeEventListener("pagehide", record);
      observer.disconnect();
    };
  }, [url, identity]);
  useEffect(() => {
    document.title = `${title} · ${brand.name}`;
  }, [title]);
  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen((value) => !value);
      }
      if (event.key === "Escape") setMobile(false);
    }
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      if (!isDirty()) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, isDirty]);
  return (
    <>
      <div className={"h-[100dvh] bg-canvas flex overflow-hidden"}>
        <a
          className={
            "fixed top-[-60px] left-3 bg-surface [border:1px_solid_var(--os-focus)] rounded-control py-2.5 px-4 [z-index:100] [&:focus]:top-2.5"
          }
          href="#platform-main"
        >
          跳到主要内容
        </a>
        {mobile && (
          <button
            className={
              "max-[768px]:fixed max-[768px]:[inset:0] max-[768px]:bg-overlay max-[768px]:[z-index:25]"
            }
            aria-label="关闭导航"
            onClick={() => setMobile(false)}
          />
        )}
        <aside
          ref={sidebar}
          id="platform-navigation"
          className={`w-(--os-navigation-width) fixed [inset:0_auto_0_0] flex flex-col bg-canvas [padding:var(--os-space-5)_var(--os-space-4)_var(--os-space-2)] [z-index:30] overflow-hidden [scrollbar-width:thin] [scrollbar-color:transparent_transparent] [@supports_selector(::-webkit-scrollbar)]:[scrollbar-width:auto] [@supports_selector(::-webkit-scrollbar)]:[scrollbar-color:auto] [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:[background:transparent] [&::-webkit-scrollbar-thumb]:rounded-control [&::-webkit-scrollbar-thumb]:[background:transparent] [@supports_not_selector(::-webkit-scrollbar)]:[&[data-scrolling]]:[scrollbar-color:var(--os-text-muted)_transparent] [&[data-scrolling]::-webkit-scrollbar-thumb]:bg-text-muted [@media(max-height:_600px)]:overflow-y-auto [@media(max-height:_600px)]:[overscroll-behavior:contain] max-[768px]:hidden max-[768px]:[box-shadow:var(--os-shadow-drawer)] max-[768px]:[&.is-open]:flex ${mobile ? "is-open" : ""}`}
          aria-label="侧边导航"
        >
          <div
            className={
              "flex items-center justify-between gap-(--os-space-3) shrink-0 min-h-(--os-control-large) mb-(--os-space-4)"
            }
          >
            <Link
              className={
                "[--brand-logo-scale:0.85] flex items-center text-left shrink-0 [text-decoration:none]"
              }
              to="/agents"
              aria-label={brand.name}
            >
              <BrandLogo subtitle />
            </Link>
            <TooltipProvider delay={200}>
              <Tooltip
                disableHoverablePopup
                onOpenChange={(open, details) => {
                  if (!open && details.reason === "escape-key") details.event.stopPropagation();
                }}
              >
                <TooltipTrigger
                  render={
                    <a
                      className={
                        "grid [place-items:center] [flex:0_0_var(--os-control-small)] w-(--os-control-small) h-(--os-control-small) [@media(pointer:coarse)]:min-w-(--os-target-touch) [@media(pointer:coarse)]:min-h-(--os-target-touch) rounded-control text-text-muted [text-decoration:none] [touch-action:manipulation] [-webkit-tap-highlight-color:transparent] [&:hover_.de-brand-help-bubble]:[background:color-mix(in_srgb,_var(--os-brand)_16%,_var(--os-muted))] [&:hover_.de-brand-help-bubble]:text-text [&:focus-visible_.de-brand-help-bubble]:[background:color-mix(in_srgb,_var(--os-brand)_16%,_var(--os-muted))] [&:focus-visible_.de-brand-help-bubble]:text-text [&:focus-visible]:[outline:2px_solid_var(--os-focus)] [&:focus-visible]:[outline-offset:2px]"
                      }
                      href={`/help/${help}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label="功能指南（新标签页）"
                    />
                  }
                >
                  <span
                    className={
                      "de-brand-help-bubble grid [place-items:center] w-7 h-7 rounded-[var(--os-radius-panel)_var(--os-radius-panel)_var(--os-radius-panel)_var(--os-radius-small)] [background:color-mix(in_srgb,_var(--os-brand)_8%,_var(--os-muted))] text-[length:var(--os-text-title)] [font-weight:var(--os-weight-heading)] leading-[1] [transition:background-color_var(--os-motion-fast),_color_var(--os-motion-fast)]"
                    }
                    aria-hidden="true"
                  >
                    ?
                  </span>
                </TooltipTrigger>
                <TooltipContent side="right" sideOffset={8}>
                  使用指南
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          <div
            className={"flex flex-col flex-1 min-h-0 [@media(max-height:_600px)]:[flex:0_0_auto]"}
          >
            <div className={"shrink-0"}>
              <nav aria-label="平台导航">
                {navigation
                  .filter(
                    (n) =>
                      n.path !== "/rules" && (!["/brains", "/tools"].includes(n.path) || admin),
                  )
                  .map(({ path, title: label, icon: Icon }) => (
                    <NavigationItem
                      active={path === parent.path}
                      render={<Link to={path} />}
                      key={path}

                      aria-current={path === parent.path ? "page" : undefined}
                    >
                      <Icon aria-hidden="true" />
                      <span>{label}</span>
                      {data.globalTotals && path === "/agents" && (
                        <small>{data.globalTotals.agents}</small>
                      )}
                    </NavigationItem>
                  ))}
              </nav>
              {identity.permissions.includes("organization_rules:read") && (
                <nav aria-label="平台管理" className="mt-5 border-t border-border pt-3">
                  <NavigationItem
                    active={parent.path === "/rules"}
                    aria-current={parent.path === "/rules" ? "page" : undefined}
                    render={<Link to="/rules" />}
                  >
                    <resourceIdentity.rules.icon aria-hidden="true" />
                    <span>全员规范</span>
                  </NavigationItem>
                </nav>
              )}
            </div>
            <section
              className={
                "flex flex-col flex-1 min-h-0 mt-(--os-space-5) [@media(max-height:_600px)]:[flex:0_0_auto]"
              }
              aria-labelledby="favorites-heading"
            >
              <div
                className={
                  "text-text-muted text-[length:var(--os-text-caption)] py-0 px-3 mb-2 tracking-[0.07em] flex items-center justify-between gap-(--os-space-2) shrink-0"
                }
                id="favorites-heading"
              >
                <span>已收藏员工</span>
                {data.ready && (
                  <span className={"tabular-nums tracking-[normal]"}>
                    {data.globalTotals?.favorites ?? favorites.length}
                  </span>
                )}
              </div>
              <nav
                ref={favoriteList}
                className={
                  "flex flex-col flex-1 gap-(--os-favorite-stack) min-w-0 min-h-0 m-[-4px] p-1 overflow-y-auto [overscroll-behavior:contain] [scrollbar-gutter:stable] [scrollbar-width:thin] [scrollbar-color:transparent_transparent] [@supports_selector(::-webkit-scrollbar)]:[scrollbar-width:auto] [@supports_selector(::-webkit-scrollbar)]:[scrollbar-color:auto] [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-control [&::-webkit-scrollbar-thumb]:bg-transparent [@supports_not_selector(::-webkit-scrollbar)]:[&[data-scrolling]]:[scrollbar-color:var(--os-text-muted)_transparent] [&[data-scrolling]::-webkit-scrollbar-thumb]:bg-text-muted [&_>_p]:m-0 [&_>_p]:text-text-muted [&_>_p]:text-[length:var(--os-text-caption)] [&_>_p]:py-3 [&_>_p]:px-2 [@media(max-height:_600px)]:[flex:0_0_auto] [@media(max-height:_600px)]:overflow-visible [@media(max-height:_600px)]:[scrollbar-gutter:auto]"
                }
                aria-label="已收藏员工"
              >
                {favorites.map((e) => (
                  <FavoriteAgentLink
                    key={e.id}
                    name={e.name}
                    avatarId={e.avatarId}
                    to={sourceLink(`/agents/${e.id}/home`)}
                    label={`查看${e.name}的员工主页`}
                    conversationTo={
                      admin ? sourceLink(`/conversations/new?agent=${e.id}`) : undefined
                    }
                  />
                ))}
                {(data.globalTotals?.favorites ?? 0) > favorites.length && (
                  <Link to="/agents?filter=favorites">查看全部收藏</Link>
                )}
                {data.summaryFailure && (
                  <FailureNotice
                    compact
                    failure={data.summaryFailure}
                    context={{
                      operation: data.ready ? "refresh" : "initial-read",
                      resource: "agent",
                      hasUsableData: data.ready,
                    }}
                    title={data.ready ? "收藏同步失败" : "收藏加载失败"}
                    actions={[{ label: "重试", kind: "retry", onClick: data.reload }]}
                  />
                )}
                {data.ready && !data.summaryError && favorites.length === 0 && (
                  <p>收藏的员工会显示在这里</p>
                )}
              </nav>
            </section>
          </div>
          <div
            className={
              "shrink-0 mt-(--os-space-2) pt-(--os-space-1) [border-top:1px_solid_var(--os-border)] [@media(max-height:_600px)]:mt-auto"
            }
          >
            <AccountMenu
              beforeLogout={() =>
                !editing.isSaving() &&
                (!editing.isDirty() || window.confirm("配置尚未保存，确定退出登录？")) &&
                (!uploads.hasPending() ||
                  window.confirm("还有文件未上传完成，退出会取消传输，确定退出？"))
              }
            />
          </div>
        </aside>
        <div className={"workspace-region workspace-surface flex flex-col overflow-hidden"}>
          <header
            className={`${conversationPage ? "conversation-gutters" : "page-gutters"} min-h-[calc(var(--os-space-6)_*_2)] shrink-0 flex flex-wrap items-center justify-between gap-2 py-1 border-b border-workspace-border ${conversationPage ? "max-sm:h-auto max-sm:flex-wrap max-sm:gap-x-2 max-sm:gap-y-1 max-sm:py-1" : ""}`}
          >
            <div
              className={`flex flex-1 items-center gap-(--os-space-2) text-[length:var(--os-text-caption)] min-w-0 ${conversationPage ? "max-sm:w-full max-sm:flex-none" : ""}`}
            >
              <Button
                className={"hidden max-[768px]:inline-flex"}
                variant="ghost"
                size="icon-sm"
                aria-label="打开导航"
                aria-controls="platform-navigation"
                aria-expanded={mobile}
                onClick={() => setMobile(true)}
              >
                <Menu />
              </Button>
              <PageToolbarTarget kind="title">
                <PageBreadcrumb
                  parent={nested ? { label: parent.title, to: parentPath } : undefined}
                  current={title}
                />
              </PageToolbarTarget>
            </div>
            {!admin && (
              <span className={"max-[600px]:hidden text-xs"}>
                {identity.actor.kind === "guest" ? "游客浏览" : "普通用户"}
                {identity.permissions.includes("runs:create") ? " · 可对话" : " · 只读"}
              </span>
            )}
            <div
              className={`flex min-w-0 max-w-full flex-wrap items-center gap-(--os-space-2) ml-auto ${conversationPage ? "max-sm:w-full max-sm:justify-end" : ""}`}
            >
              <PageToolbarTarget kind="actions" />
              <button
                className={
                  "flex items-center gap-[9px] shrink-0 w-56 min-w-0 min-h-(--os-control-small) py-0 px-[9px] [border:1px_solid_var(--os-border)] rounded-control bg-canvas text-text-muted text-[length:var(--os-text-caption)] text-left [&_>_svg]:shrink-0 [&_>_span]:min-w-0 [&_>_span]:overflow-hidden [&_>_span]:text-ellipsis [&_>_span]:whitespace-nowrap [&:hover]:bg-muted [&_kbd]:ml-auto [&_kbd]:text-[length:var(--os-text-caption)] [&_kbd]:whitespace-nowrap [&_kbd]:[border:1px_solid_var(--os-border)] [&_kbd]:rounded-small [&_kbd]:py-[1px] [&_kbd]:px-1 max-[1100px]:justify-center max-[1100px]:w-(--os-control-small) max-[1100px]:p-0 max-[1100px]:[border-color:transparent] max-[1100px]:bg-transparent max-[1100px]:[&_>_span]:hidden max-[1100px]:[&_kbd]:hidden"
                }
                aria-label="全局搜索员工或技能"
                aria-haspopup="dialog"
                aria-expanded={searchOpen}
                onClick={() => setSearchOpen(true)}
              >
                <Search size={16} aria-hidden="true" />
                <span>全局搜索</span>
                <kbd>⌘ K</kbd>
              </button>
              <ThemeSwitcher />
            </div>
          </header>
          {transition.state !== "idle" && (
            <div
              className={
                "fixed top-2 left-[50%] [z-index:60] bg-surface [border:1px_solid_var(--os-border)] py-1.5 px-3 rounded-control text-[length:12px]"
              }
              role="status"
            >
              正在打开页面…
            </div>
          )}
          <main
            ref={main}
            id="platform-main"
            tabIndex={-1}
            className={`[scrollbar-width:none] [&::-webkit-scrollbar]:hidden flex-1 min-h-0 overflow-y-auto [overscroll-behavior:contain] ${location.pathname.startsWith("/conversations/") ? "overflow-hidden [&_>_.de-route-content]:h-full [&_>_.de-route-content]:w-full [&_>_.de-route-content]:min-h-0" : ""}`}
          >
            <div className="de-route-content flex min-h-full flex-col" key={location.pathname}>
              <Outlet />
            </div>
          </main>
        </div>
      </div>
      <KnowledgeUploadPanel />
      <Dialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open && blocker.state === "blocked") blocker.reset();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{saving ? "正在保存" : "放弃未保存的修改？"}</DialogTitle>
            <DialogDescription>
              {saving
                ? "请等待保存完成，再切换页面。"
                : "放弃后将清除当前草稿，恢复上次保存的配置。"}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => blocker.state === "blocked" && blocker.reset()}
            >
              继续编辑
            </Button>
            <Button
              disabled={saving}
              onClick={() => {
                if (editing.isSaving()) return;
                editing.discard();
                if (blocker.state === "blocked") blocker.proceed();
              }}
            >
              放弃修改并离开
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={searchOpen} onOpenChange={setSearchOpen}>
        <DialogContent className={"dialog-standard [&_.de-search-input]:w-full"}>
          <DialogHeader>
            <DialogTitle>全局搜索</DialogTitle>
            <DialogDescription>按名称和用途搜索员工与技能。</DialogDescription>
          </DialogHeader>
          <SearchInput
            className="w-full"
            label="搜索员工或技能"
            value={search}
            onChange={setSearch}
            debounceMs={300}
          />
          {searchOpen && (
            <GlobalSearch
              query={search}
              onNavigate={(path) => {
                setSearchOpen(false);
                navigate(path);
              }}
            />
          )}
          <Button variant="ghost" onClick={() => setSearchOpen(false)}>
            <X size={14} />
            关闭
          </Button>
        </DialogContent>
      </Dialog>
    </>
  );
}
