import { createBrowserRouter, Navigate, Outlet, useSearchParams } from "react-router";
import { AuthBoundary } from "./components/auth/AuthBoundary";
import { safeReturnPath } from "@/lib/navigation";
import { RouteFailure, RouteNotFound, routeModule } from "@/components/failure/RouteFailure";

function LegacyEntry() {
  const [params] = useSearchParams();
  const agent = params.get("agent");
  const task = params.get("task");
  if (agent) {
    const query = new URLSearchParams();
    if (params.get("tab")) query.set("tab", params.get("tab")!);
    return (
      <Navigate
        replace
        to={`/agents/${encodeURIComponent(agent)}${query.size ? `?${query}` : ""}`}
      />
    );
  }
  if (task) return <Navigate replace to={`/conversations/new?agent=${encodeURIComponent(task)}`} />;
  return <Navigate replace to="/agents" />;
}

function ProtectedPreview() {
  return (
    <AuthBoundary permission="agents:read">
      <Outlet />
    </AuthBoundary>
  );
}

function InitialLoading() {
  return (
    <main className="page-frame py-6" aria-busy="true">
      <p role="status">正在打开页面…</p>
    </main>
  );
}

function LoginAlias() {
  const [params] = useSearchParams();
  return (
    <Navigate
      replace
      to={`/signin?next=${encodeURIComponent(safeReturnPath(params.get("next")))}`}
    />
  );
}

export const router = createBrowserRouter([
  ...(import.meta.env.DEV
    ? [
        {
          path: "/demo/failures",
          lazy: routeModule(async () => ({
            Component: (await import("./pages/design-system/FailureDemoPage")).FailureDemoPage,
          })),
          hydrateFallbackElement: <InitialLoading />,
          errorElement: <RouteFailure />,
        },
        {
          path: "/demo/capabilities",
          lazy: routeModule(async () => ({
            Component: (await import("./pages/design-system/CapabilityDemoPage"))
              .CapabilityDemoPage,
          })),
          hydrateFallbackElement: <InitialLoading />,
          errorElement: <RouteFailure />,
        },
      ]
    : []),
  { path: "/", element: <LegacyEntry />, errorElement: <RouteFailure /> },
  { path: "/login", Component: LoginAlias },
  {
    path: "/signin",
    errorElement: <RouteFailure />,
    lazy: routeModule(() => import("./pages/signin/SigninPage")),
    hydrateFallbackElement: <InitialLoading />,
  },
  { path: "/preview", element: <Navigate replace to="/agents" /> },
  {
    lazy: routeModule(async () => ({ Component: (await import("./Layout")).Layout })),
    hydrateFallbackElement: <InitialLoading />,
    errorElement: <RouteFailure />,
    children: [
      {
        errorElement: <RouteFailure layout="section" />,
        children: [
          { path: "/agents", lazy: routeModule(() => import("./pages/agents/AgentsPage")) },
          {
            path: "/agents/:id/home",
            lazy: routeModule(async () => ({
              Component: (await import("./pages/agents/EmployeeHomePage")).EmployeeHomePage,
            })),
          },
          {
            path: "/agents/new",
            lazy: routeModule(async () => ({
              Component: (await import("./pages/agents/AgentsPage")).AgentEditorPage,
            })),
          },
          {
            path: "/agents/:id",
            lazy: routeModule(async () => ({
              Component: (await import("./pages/agents/AgentsPage")).AgentEditorPage,
            })),
          },
          { path: "/skills", lazy: routeModule(() => import("./pages/skills/CapabilitiesPage")) },
          {
            path: "/skills/new",
            lazy: routeModule(async () => ({
              Component: (await import("./pages/skills/SkillEditorPage")).SkillEditorPage,
            })),
          },
          {
            path: "/skills/:id",
            lazy: routeModule(async () => ({
              Component: (await import("./pages/skills/SkillEditorPage")).SkillEditorPage,
            })),
          },
          {
            path: "/rules",
            lazy: routeModule(() => import("./pages/organization-rules/OrganizationRulesPage")),
          },
          { path: "/brains", lazy: routeModule(() => import("./pages/brains/BrainsPage")) },
          {
            path: "/agents/:id/connections",
            lazy: routeModule(() => import("./pages/tools/PersonalConnectionsPage")),
          },
          { path: "/tools", lazy: routeModule(() => import("./pages/tools/ToolsPage")) },
          {
            path: "/knowledge",
            lazy: routeModule(() => import("./pages/knowledge/KnowledgePage")),
          },
          {
            path: "/knowledge/:id",
            lazy: routeModule(() => import("./pages/knowledge/KnowledgePage")),
          },
          {
            path: "/knowledge/:id/documents/:documentId",
            lazy: routeModule(() => import("./pages/knowledge/KnowledgePage")),
          },
          {
            path: "/conversations",
            lazy: routeModule(() => import("./pages/conversations/ConversationsPage")),
          },
          {
            path: "/conversations/new",
            lazy: routeModule(async () => ({
              Component: (await import("./pages/conversations/ConversationsPage")).ConversationPage,
            })),
          },
          {
            path: "/conversations/:id/trace",
            lazy: routeModule(async () => ({
              Component: (await import("./pages/conversations/ExecutionTracePage"))
                .ExecutionTracePage,
            })),
          },
          {
            path: "/agents/:id/evaluations/:batchId/cases/:caseId/trace",
            lazy: routeModule(async () => ({
              Component: (await import("./pages/conversations/ExecutionTracePage"))
                .ExecutionTracePage,
            })),
          },
          {
            path: "/conversations/:id",
            lazy: routeModule(async () => ({
              Component: (await import("./pages/conversations/ConversationsPage")).ConversationPage,
            })),
          },
        ],
      },
    ],
  },
  {
    path: "/help/:topic?",
    errorElement: <RouteFailure />,
    lazy: routeModule(() => import("./pages/help/HelpPage")),
    hydrateFallbackElement: <InitialLoading />,
  },
  {
    element: <ProtectedPreview />,
    errorElement: <RouteFailure />,
    hydrateFallbackElement: <InitialLoading />,
    children: [
      {
        path: "/design-system",
        lazy: routeModule(async () => ({
          Component: (await import("./pages/design-system/DesignSystemPage")).DesignSystemPage,
        })),
      },
      {
        path: "/avatars/svg",
        lazy: routeModule(async () => ({
          Component: (await import("./pages/avatars/AvatarGalleryPage")).AvatarGalleryPage,
        })),
      },
      { path: "/avatars/playground", element: <Navigate replace to="/avatars/svg" /> },
      { path: "/avatars/playground/:role", element: <Navigate replace to="/avatars/svg" /> },
      {
        path: "/avatars/rive/programmer",
        element: <Navigate replace to="/avatars/svg" />,
      },
    ],
  },
  { path: "*", Component: RouteNotFound },
]);

// 路由模块替换后，旧实例不应继续监听浏览器历史或处理在途导航。
if (import.meta.hot) import.meta.hot.dispose(() => router.dispose());
