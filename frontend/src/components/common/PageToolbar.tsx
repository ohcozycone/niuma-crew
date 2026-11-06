import { createContext, useContext, useLayoutEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

type Toolbar = {
  title: HTMLDivElement | null;
  actions: HTMLDivElement | null;
  active: boolean;
  setTitle: (node: HTMLDivElement | null) => void;
  setActions: (node: HTMLDivElement | null) => void;
  setActive: (active: boolean) => void;
};
const Context = createContext<Toolbar | null>(null);

/** 页面借用共享导航栏的插槽，交互状态仍归页面所有。 */
export function PageToolbarProvider({ children }: { children: ReactNode }) {
  const [title, setTitle] = useState<HTMLDivElement | null>(null);
  const [actions, setActions] = useState<HTMLDivElement | null>(null);
  const [active, setActive] = useState(false);
  return (
    <Context.Provider value={{ title, actions, active, setTitle, setActions, setActive }}>
      {children}
    </Context.Provider>
  );
}

export function PageToolbarTarget({
  kind,
  children,
}: {
  kind: "title" | "actions";
  children?: ReactNode;
}) {
  const toolbar = useContext(Context);
  return (
    <>
      {kind === "title" && !toolbar?.active && children}
      <div
        ref={kind === "title" ? toolbar?.setTitle : toolbar?.setActions}
        className={
          !toolbar?.active
            ? "hidden"
            : kind === "title"
              ? "min-w-0 flex-1"
              : "flex min-w-0 flex-1 flex-wrap items-center gap-1"
        }
      />
    </>
  );
}

export function PageToolbar({ title, actions }: { title: ReactNode; actions: ReactNode }) {
  const toolbar = useContext(Context);
  const setActive = toolbar?.setActive;
  useLayoutEffect(() => {
    setActive?.(true);
    return () => setActive?.(false);
  }, [setActive]);
  // 独立预览和测试没有共享外壳时仍保留身份与操作入口。
  if (!toolbar)
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-2 px-4 py-2">
        {title}
        {actions}
      </div>
    );
  return (
    <>
      {toolbar.title && createPortal(title, toolbar.title)}
      {toolbar.actions && createPortal(actions, toolbar.actions)}
    </>
  );
}
