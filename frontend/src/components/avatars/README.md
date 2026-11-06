# 数字形象组件

本模块负责当前十三角色彩色 SVG 的岗位映射、统一渲染和头像选择。员工卡片、导航、配置与对话共用此入口；页面不拼素材路径。主工程只维护静态头像。

## 项目内使用

```tsx
import { AgentAvatar, AvatarBadge, AvatarPicker } from "@/components/avatars";

<AgentAvatar avatarId="designer" size={96} alt="设计师牛" />;
<AvatarBadge avatarId="admin" size="navigation" />;
```

`AgentAvatar` 接收 `avatarId`、`size`（默认 96，可为 CSS 尺寸）、`alt`（默认空，表示装饰性）与 `className`。应用按实际角色加载对应模块，渲染内联 SVG；加载期间保留同样的尺寸，不额外引入图片或动画运行时。独立 `SvgAvatar` 与具名组件保留同步渲染接口。渐变、裁剪和透明蒙版 ID 按实例隔离；研究马镜片保留原生透明蒙版，组件与同版母版的真实 SSR 像素一致。

`AvatarBadge` 提供 `small`、`normal`、`large` 及 `navigation` 尺寸；收藏员工使用 `navigation`。导航头像及列表的尺寸、透明无框外观与整行状态统一由[设计系统](../../design-system/components.md#员工头像导航)规定。头像旁已有姓名时保持装饰性，由整行链接提供名称与跳转入口。

| 稳定岗位 ID  | 当前形象   | 矢量组件 character |
| ------------ | ---------- | ------------------ |
| `intern`     | 实习生牛   | `intern-bull`      |
| `finance`    | 财务牛     | `finance-bull`     |
| `admin`      | 行政牛     | `admin-bull`       |
| `designer`   | 设计师牛   | `designer-bull`    |
| `programmer` | 程序员马   | `programmer-horse` |
| `backend`    | 后端马     | `backend-horse`    |
| `frontend`   | 前端牛     | `frontend-bull`    |
| `product`    | 产品经理马 | `product-horse`    |
| `sysadmin`   | 运维马     | `sysadmin-horse`   |
| `knowledge`  | 知识牛     | `knowledge-bull`   |
| `research`   | 研究马     | `research-horse`   |
| `operations` | 运营牛     | `operations-bull`  |
| `support`    | 客服马     | `support-horse`    |

`AvatarPicker` 使用宽高相同的正方形选项，图片居中并等比适配可用空间；直接展示十三张图片与选中标记，不提供搜索或系列筛选，不显示岗位名称、职责、格式标签或悬停说明；按钮使用「头像 + 序号」作为无障碍名称。员工配置页的当前头像区也不显示图片对应的岗位名。对应岗位的历史别名解析到当前形象，包括新恢复的运营和客服；仍退出的销售、数据、HR、法务、采购及未知 ID 使用默认实习生牛显示。`findAvatar` 对这些未提供角色返回 undefined，所以更改其他员工字段不会顺带改写原 `avatar_id`；明确选择角色后才保存新的稳定 ID。无需数据库批量迁移。

「实习生牛」原图与无描边 SVG 已认可，已接入并设为默认，位于选择器首位。新建初始头像使用 `intern`；已有员工明确选择和未知旧 ID 不改写。后端马、前端牛已按认可 SVG 接入，可使用 `avatarId="backend"` / `avatarId="frontend"` 或具名矢量组件。

独立美术场景可直接使用十三角色组件：

```tsx
import { SvgAvatar, DesignerBullAvatar } from "@/components/avatars";

<SvgAvatar character="designer-bull" size={96} alt="设计师牛" />;
<DesignerBullAvatar size={48} background="#fff9ef" />;
```

支持 `background`、`style` 和原生 SVG 属性；需要按角色导入时使用 `@/components/avatars/svg/designer-bull`。`svg/package.json` 标记这些模块无导入副作用，供构建器按实际引用拆包。

## 维护入口

- [registry.ts](../../lib/avatars/registry.ts) 读取[正式目录](../../../public/avatars/catalog.json)的稳定 ID、SVG 映射与历史别名。`frontend/scripts/build-avatar-manifest.mjs` 为浏览器生成同源快照，正常开发、测试与构建自动更新。
- [AgentAvatar.tsx](AgentAvatar.tsx) 提供显示回退；[AvatarPicker.tsx](AvatarPicker.tsx) 共用同一目录，防止展示与可选资源脱节。
- [svg/](svg) 保存实际渲染实现和十三角色数据；可编辑母版已迁至独立归档。资源边界与验证见 [SVG 母版与组件](../../../../docs/reference/avatar-assets.md)。
- 预览 `/avatars/svg` 沿用员工读取权限；旧动画预览入口跳转到此页。
- 旧黑白公开资产、旧目录与角色设定移至内部档案，不随前端构建发布。当前角色依据见 [CHARACTERS.md](CHARACTERS.md)。

## 验证

在仓库根执行 `make test-avatars`、`make lint-frontend`，交付影响执行 `make build`。检查十三角色映射、历史 ID 与显示回退、SSR、多实例裁剪、资源存在和无旧黑白公开目录；浏览器核对员工页、头像选择、导航、移动端和旧预览跳转。API 回归检查显示回退不会改变存量 ID。母版到组件的逐像素验证工具与历史证据保存在独立归档目录。
