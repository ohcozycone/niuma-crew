# 角色 SVG 母版与静态组件

本文维护当前行为或操作，历史结果按记录索引查阅；未执行的目标能力不属于本页已实现范围。

## 资源与组件边界

主工程仅保留正式静态头像。可编辑母版已迁至独立归档的 source/masters，许可在 LICENSE；主工程浏览器 SVG 在 `frontend/public/avatars/svg/`，本地 React 渲染实现与十三角色数据在 `frontend/src/components/avatars/svg/`。运行和构建不读取原图或制作工程，不依赖头像包、Rive 或 WASM。

统一 `0 0 1254 1254` viewBox 与透明背景，保留稳定形状名称、原生渐变、裁剪与透明镜片。不嵌入位图、外链、字体、脚本或滤镜；正式 SVG 不用描边遮盖轮廓。内联 SVG 的渐变、裁剪和蒙版引用按实例隔离，支持 SSR。静态形体不表示已具备活动件、关节或动画绑定。

应用统一从 `@/components/avatars` 使用 `AgentAvatar`、`AvatarBadge`、`AvatarPicker`、`SvgAvatar` 和具名角色组件。属性、十三岗位映射、默认实习牛、未知旧 ID 的显示回退及不改写存量 ID 的规则，以[组件 README](../../frontend/src/components/avatars/README.md)为准。

`/avatars/svg` 提供角色、大小、背景与放大预览，沿用 `agents:read` 权限。旧动画 URL 继续跳转静态图库。

## 维护与验证

`frontend/public/avatars/catalog.json` 维护稳定岗位 ID、角色映射与历史别名；`frontend/scripts/build-avatar-manifest.mjs` 在开发、测试、类型检查和构建时生成同源快照。应用资源哈希记录在 `frontend/public/avatars/svg/catalog.json`；归档母版的哈希清单位于独立工程 `artwork/avatar-svg/source/masters/manifest.json`。本次迁移时十三张母版与应用 SVG 字节一致，后续不自动同步。

日常验证在 `frontend` 执行 `pnpm test:avatars`、`pnpm typecheck`、`pnpm lint`、`pnpm build`。现有测试覆盖十三角色与公开文件、旧 ID 显示回退、SSR 及多实例引用隔离。从独立工程导入 SVG 变更时，同时核对认可母版、应用 SVG、组件数据与哈希清单，并在真实页面复核选择、保存回显、导航、对话和移动端。

原图、认可记录、重建/导出工具、Rive 素材和全部历史样片迁至独立 `niuma-crew-archive`。制作步骤及此前逐像素验证见归档制作说明，目录边界、迁移与恢复见[素材隔离设计](../guides/assets.md)。主工程不再提供头像制作命令。

2026-10-21 的十三角色接入验证保存在独立目录的像素与母版记录和页面回归。这两项是历史验证，本次迁移结果另见素材隔离设计。
