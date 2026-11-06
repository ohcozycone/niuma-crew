# 组件源码与类型清单

盘点日期：2026-10-31。范围为 `components/` 和 `pages/` 下自有非测试 TSX 文件；排除测试、fixtures、SVG 角色原画与纯逻辑 TS 文件。此清单用于核对规范覆盖，不把文件数称为组件数，也不把 Provider、Context 或页面包装当成新的视觉类型。

当前盘点纳入 **114 个 TSX 文件**：基础 UI 21 个，共享层共 57 个（含基础 UI），页面及其私有展示文件 57 个。原完整盘点的106个文件及引用清单保留在本轮记录作为当时时点；其后增加4个共享反馈文件、2个页面示例、共享 ModelConnections 和页面私有 KnowledgeCard。各文件均映射到[组件分类](component-catalog.md)，不把114个文件表述为均经浏览器覆盖。角色原画的各角色由[头像资源契约](../../../docs/reference/avatar-assets.md)维护，不将十三个角色枚举成十三套 UI 规范。

构建出的 JSX 内部函数和子组件归所属文件，类型差异在规范中枚举；纯类型、样式对象、工具函数和上下文常量没有独立视觉规范。当前生效规则和实施状态见[布局规范](layout.md)和实施方案。

2026-11-01引用展示新增[HoverCard](../components/ui/HoverCard.tsx)（C23，Base UI PreviewCard浮层）和[Sources](../components/ui/Sources.tsx)（C19，来源折叠目录）；知识适配[KnowledgeInlineCitation](../components/knowledge/KnowledgeInlineCitation.tsx)和[KnowledgeSources](../components/knowledge/KnowledgeSources.tsx)归C16/C19/C23。它们复用既有语义令牌及Button/Trace，片段读取在业务适配和KnowledgeStore中处理。上方数量保留原盘点时点，正式对话页为本组合的真实使用样板。

## 基础 UI

| 实现入口                                                        | 类型归属  |
| --------------------------------------------------------------- | --------- |
| [Badge](../components/ui/Badge.tsx)                             | C13       |
| [Bubble](../components/ui/Bubble.tsx)                           | C18       |
| [Button](../components/ui/Button.tsx)                           | C01       |
| [ButtonGroup](../components/ui/ButtonGroup.tsx)                 | C01       |
| [Card](../components/ui/Card.tsx)                               | C08       |
| [Collapsible](../components/ui/Collapsible.tsx)                 | C26       |
| [Dialog](../components/ui/Dialog.tsx)                           | C22       |
| [DropdownMenu](../components/ui/DropdownMenu.tsx)               | C23       |
| [Field](../components/ui/Field.tsx)                             | C02       |
| [Form](../components/ui/Form.tsx)                               | C02       |
| [Input](../components/ui/Input.tsx)                             | C02       |
| [InputGroup](../components/ui/InputGroup.tsx)                   | C02 / C18 |
| [Message](../components/ui/Message.tsx)                         | C18       |
| [MessageScroller](../components/ui/MessageScroller.tsx)         | C18 / C26 |
| [NavigationItem](../components/ui/NavigationItem.tsx)           | C05       |
| [Select（内部基础适配）](../components/ui/Select.tsx)           | C03 / C23 |
| [SelectField（统一选择入口）](../components/ui/SelectField.tsx) | C03 / C23 |
| [Switch](../components/ui/Switch.tsx)                           | C03       |
| [Tabs](../components/ui/Tabs.tsx)                               | C07       |
| [Textarea](../components/ui/Textarea.tsx)                       | C02       |
| [Tooltip](../components/ui/Tooltip.tsx)                         | C23       |
| [Trace](../components/ui/Trace.tsx)                             | C19       |

## 共享组合（不含基础 UI）

全站语义迁移新增 [ResourceIcon](../components/common/ResourceIcon.tsx)（C13，对象标识）与 [ConfirmActionDialog](../components/common/ConfirmActionDialog.tsx)（C22，危险操作确认），复用现有基础组件。上方总数保留原扫描时点，不代表当前新增文件数量。

| 实现入口                                                                                                                                                                                                                             | 类型归属        |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------- |
| [ModelConnections](../components/configuration/ModelConnections.tsx)                                                                                                                                                                 | C03 / C12 / C22 |
| [AccountMenu](../components/auth/AccountMenu.tsx)                                                                                                                                                                                    | C05             |
| [AccountMenuButton](../components/auth/AccountMenuButton.tsx)                                                                                                                                                                        | C05             |
| [AuthBoundary](../components/auth/AuthBoundary.tsx)                                                                                                                                                                                  | C21 / C26       |
| [AgentAvatar](../components/avatars/AgentAvatar.tsx)                                                                                                                                                                                 | C24             |
| [AvatarBadge](../components/avatars/AvatarBadge.tsx)                                                                                                                                                                                 | C24             |
| [AvatarPicker](../components/avatars/AvatarPicker.tsx)                                                                                                                                                                               | C22 / C24       |
| [LazySvgAvatar](../components/avatars/LazySvgAvatar.tsx)                                                                                                                                                                             | C24             |
| [BrandLogo](../components/brand/BrandLogo.tsx)                                                                                                                                                                                       | C24             |
| [EmptyState](../components/common/EmptyState.tsx)                                                                                                                                                                                    | C21             |
| [FailureState](../components/failure/FailureState.tsx)、[FailureNotice](../components/failure/FailureNotice.tsx)、[FailureActions](../components/failure/FailureActions.tsx)、[RouteFailure](../components/failure/RouteFailure.tsx) | C21 / C26       |
| [FormField](../components/common/FormField.tsx)                                                                                                                                                                                      | C02             |
| [Markdown](../components/common/Markdown.tsx)                                                                                                                                                                                        | C15 / C16 / C17 |
| [PageBreadcrumb](../components/common/PageBreadcrumb.tsx)                                                                                                                                                                            | C05             |
| [PageContainer](../components/common/PageContainer.tsx)                                                                                                                                                                              | C26             |
| [PageHeading](../components/common/PageHeading.tsx)                                                                                                                                                                                  | C06             |
| [PageActionsMenu](../components/common/PageActionsMenu.tsx)                                                                                                                                                                          | C05 / C06       |
| [CollectionToolbar](../components/common/CollectionToolbar.tsx)                                                                                                                                                                      | C04 / C06       |
| [PageTabs](../components/common/PageTabs.tsx)                                                                                                                                                                                        | C07 / C26       |
| [PageToolbar](../components/common/PageToolbar.tsx)                                                                                                                                                                                  | C06 / C26       |
| [Pagination](../components/ui/Pagination.tsx)                                                                                                                                                                                        | C07             |
| [ResourcePagination](../components/common/ResourcePagination.tsx)                                                                                                                                                                    | C07             |
| [SearchInput](../components/common/SearchInput.tsx)                                                                                                                                                                                  | C04             |
| [AssemblyItem](../components/configuration/AssemblyItem.tsx)                                                                                                                                                                         | C14             |
| [ConfigurationConflict](../components/configuration/ConfigurationConflict.tsx)                                                                                                                                                       | C21             |
| [ResourceStatus](../components/configuration/ResourceStatus.tsx)                                                                                                                                                                     | C21 / C26       |
| [StaleDraftNotice](../components/configuration/StaleDraftNotice.tsx)                                                                                                                                                                 | C21             |
| [FavoriteAgentLink](../components/navigation/FavoriteAgentLink.tsx)                                                                                                                                                                  | C05             |
| [GlobalSearch](../components/navigation/GlobalSearch.tsx)                                                                                                                                                                            | C04 / C13 / C23 |
| [InheritedRules](../components/organization-rules/InheritedRules.tsx)                                                                                                                                                                | C12 / C26       |
| [CapabilityCard](../components/skills/CapabilityCard.tsx)                                                                                                                                                                            | C10             |
| [SkillCard](../components/skills/SkillCard.tsx)                                                                                                                                                                                      | C10             |
| [ThemeArtwork](../components/theme/ThemeArtwork.tsx)                                                                                                                                                                                 | C24             |
| [ThemeSwitcher](../components/theme/ThemeSwitcher.tsx)                                                                                                                                                                               | C05 / C24       |
| [ToolAssembly](../components/tools/ToolAssembly.tsx)                                                                                                                                                                                 | C14 / C22       |

## 页面与私有展示

新增 [AgentCapabilityAssembly](../pages/agents/AgentCapabilityAssembly.tsx)（C04 / C14 / C22，混合装配）与 [ResourceLanguageExamples](../pages/design-system/ResourceLanguageExamples.tsx)（C25，正式组件样板）。

| 实现入口                                                                              | 类型归属                    |
| ------------------------------------------------------------------------------------- | --------------------------- |
| [AgentCard](../pages/agents/AgentCard.tsx)                                            | C09                         |
| [AgentConfiguration](../pages/agents/AgentConfiguration.tsx)                          | C12 / C26                   |
| [AgentDeletionDialog](../pages/agents/AgentDeletionDialog.tsx)                        | C22                         |
| [AgentDirectory](../pages/agents/AgentDirectory.tsx)                                  | C04 / C09                   |
| [AgentModelConnectionField](../pages/agents/AgentModelConnectionField.tsx)            | C03 / C12                   |
| [AgentSkillAssembly](../pages/agents/AgentSkillAssembly.tsx)                          | C14 / C22                   |
| [AgentsPage](../pages/agents/AgentsPage.tsx)                                          | C09 / C12 / C26             |
| [AvatarGalleryPage](../pages/avatars/AvatarGalleryPage.tsx)                           | C24 / C25                   |
| [BrainWorkspace](../pages/brains/BrainWorkspace.tsx)                                  | C11 / C12 / C22             |
| [BrainsPage](../pages/brains/BrainsPage.tsx)                                          | C11 / C26                   |
| [ConversationComposer](../pages/conversations/ConversationComposer.tsx)               | C18 / C20                   |
| [ConversationControls](../pages/conversations/ConversationControls.tsx)               | C18 / C21                   |
| [ConversationFiles](../pages/conversations/ConversationFiles.tsx)                     | C20                         |
| [ConversationHistory](../components/conversations/ConversationHistory.tsx)            | C07 / C13                   |
| [ConversationMessage](../pages/conversations/ConversationMessage.tsx)                 | C15 / C16 / C17 / C18       |
| [ConversationOutline](../pages/conversations/ConversationOutline.tsx)                 | C19 / C23                   |
| [ConversationPanel](../pages/conversations/ConversationPanel.tsx)                     | C18 / C26                   |
| [ConversationTranscript](../pages/conversations/ConversationTranscript.tsx)           | C18 / C19 / C26             |
| [ConversationProvider](../pages/conversations/ConversationProvider.tsx)               | C26                         |
| [ConversationQuestionPreview](../pages/conversations/ConversationQuestionPreview.tsx) | C19 / C23                   |
| [ConversationRuler](../pages/conversations/ConversationRuler.tsx)                     | C19                         |
| [ConversationsPage](../pages/conversations/ConversationsPage.tsx)                     | C13 / C18 / C26             |
| [RunActions](../pages/conversations/RunActions.tsx)                                   | C19                         |
| [CapabilityDemoPage](../pages/design-system/CapabilityDemoPage.tsx)                   | C25                         |
| [ColorCatalog](../pages/design-system/ColorCatalog.tsx)                               | C25                         |
| [ComponentExamples](../pages/design-system/ComponentExamples.tsx)                     | C25                         |
| [DemoInvocationDialog](../pages/design-system/DemoInvocationDialog.tsx)               | C22 / C25                   |
| [DesignSystemPage](../pages/design-system/DesignSystemPage.tsx)                       | C25                         |
| [LayoutCatalog](../pages/design-system/LayoutCatalog.tsx)                             | C02 / C25                   |
| [McpCatalogManager](../pages/design-system/McpCatalogManager.tsx)                     | C12 / C25                   |
| [PatternExamples](../pages/design-system/PatternExamples.tsx)                         | C25                         |
| [TypographyCatalog](../pages/design-system/TypographyCatalog.tsx)                     | C25                         |
| [HelpPage](../pages/help/HelpPage.tsx)                                                | C16 / C25                   |
| [KnowledgeCard](../pages/knowledge/KnowledgeCard.tsx)                                 | C08                         |
| [KnowledgeLibraries](../pages/knowledge/KnowledgeLibraries.tsx)                       | C02 / C04 / C06 / C08 / C13 |
| [KnowledgeLibrary](../pages/knowledge/KnowledgeLibrary.tsx)                           | C02 / C04 / C08 / C13 / C21 |
| [KnowledgeSearch](../pages/knowledge/KnowledgeSearch.tsx)                             | C04 / C13 / C16 / C21       |
| [KnowledgeVectors](../pages/knowledge/KnowledgeVectors.tsx)                           | C03 / C12 / C21             |
| [KnowledgeDocumentPage](../pages/knowledge/KnowledgeDocumentPage.tsx)                 | C06 / C08 / C16 / C22       |
| [KnowledgePage](../pages/knowledge/KnowledgePage.tsx)                                 | C07 / C26                   |
| [OrganizationRulesPage](../pages/organization-rules/OrganizationRulesPage.tsx)        | C12 / C16                   |
| [SigninPage](../pages/signin/SigninPage.tsx)                                          | C25                         |
| [CapabilitiesPage](../pages/skills/CapabilitiesPage.tsx)                              | C04 / C10                   |
| [SkillEditor](../pages/skills/SkillEditor.tsx)                                        | C12 / C17                   |
| [SkillEditorPage](../pages/skills/SkillEditorPage.tsx)                                | C17 / C26                   |
| [SkillLibrarySync](../pages/skills/SkillLibrarySync.tsx)                              | C12 / C22                   |
| [SkillPackageImport](../pages/skills/SkillPackageImport.tsx)                          | C20 / C22                   |
| [ConnectionSettings](../pages/tools/ConnectionSettings.tsx)                           | C11 / C12                   |
| [DeleteToolDialog](../pages/tools/DeleteToolDialog.tsx)                               | C22                         |
| [McpQuickImport](../pages/tools/McpQuickImport.tsx)                                   | C12 / C22                   |
| [McpSetupAccess](../pages/tools/McpSetupAccess.tsx)                                   | C12                         |
| [PersonalConnectionsPage](../pages/tools/PersonalConnectionsPage.tsx)                 | C11 / C12 / C26             |
| [ToolCatalogEditor](../pages/tools/ToolCatalogEditor.tsx)                             | C12 / C17                   |
| [ToolsPage](../pages/tools/ToolsPage.tsx)                                             | C11 / C12 / C26             |

## 覆盖边界

`Layout.tsx` 与 `router.tsx` 在上述扫描目录之外，分别归 C05/C06/C26 和页面模式装配。生成的头像注册表、图形素材、主题控制器与业务 Hook 不另造视觉类型，变化时核对它们所服务的正式组件。

访问异常新增的[真实组合示例](../pages/design-system/FailureExamples.tsx)及[开发预览包装](../pages/design-system/FailureDemoPage.tsx)归C21/C25/C26，复用上述共享组件，不是第二套错误页实现。

本清单证明文件被分类，不代表每种状态、键盘行为或每个浏览器已实测。
