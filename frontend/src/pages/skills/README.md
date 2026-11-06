# 能力库发现与技能编辑

能力库把技能和 MCP 服务放在同一检索入口，用户按名称和类型查找后进入各自管理。技能编辑器负责主文、支持文件和展示属性；导入或保存得到共享资产，仍需在员工中选择后参与工作。

## 模块设计

### 一个列表如何接续不同能力

标题右侧“添加能力”聚合新建技能、导入技能包和接入 MCP。更多菜单集中服务器目录同步、内置文件与代码工具和重新加载；搜索、类型筛选、结果摘要复用 CollectionToolbar。同步弹窗独立于菜单挂载，关闭后回焦更多入口，只在明确提交后扫描目录。内置工具入口配置文件/代码操作的访问方式，保存后仍需员工装配。

`CapabilitiesPage` 使用 URL 表达搜索、类型和分页，通过 WorkspaceData 读取服务器已合并的结果；前端不分别取两份列表再拼页。技能条目进入技能编辑，MCP 条目转到工具模块；统一卡片只提供发现展示，不合并两类业务生命周期。

### 标准包为何整份读取、整份提交

`SkillEditorPage` 和 `useSkillEditor` 连接路由、完整详情和保存操作，`SkillEditor` 管正文及文件树。已有包先读取全部支持文件，任一失败就阻止整包保存，避免把「尚未加载」误当「用户删除」。提交包含主文、完整文件集合、平台属性及预期修订。

正文采用 SKILL.md，展示别名、分类和参数规范是平台属性。旧字段保留但不建立第二份正文编辑来源。参数面板只消费明确规范，技能正文不会让前端自动生成工具许可。

### 导入、同步和保存如何更新工作台

ZIP 导入先请求服务器预览，再明确确认同一包，并跳到同一编辑器；目录同步展示后端实际目录及逐包结果，普通刷新不扫描宿主。保存、导入和同步统一通过 SkillStore，WorkspaceData 使能力库、员工摘要、数量和搜索重新核对，页面不重复广播全局变化。

正文及元数据可恢复标签页草稿，新增资源修改只留当前页面，离页保护提示未保存。服务端版本或外部目录冲突时保留输入，核对后再提交；上传脚本不会执行或安装依赖。

## 目录与职责

```text
skills/
├── CapabilitiesPage.tsx           # 将 URL 条件连接到联合能力目录，组织类型卡片和不同添加/管理入口
├── SkillEditorPage.tsx            # 装配创建或编辑页面，连接路由返回、身份与未保存保护
├── useSkillEditor.ts              # 读取完整技能和共享保存操作，管理加载/保存状态及返回的确认版本
├── SkillEditor.tsx                # 编辑 SKILL.md、平台属性及完整支持文件，加载失败时阻止误删式整包保存
├── SkillPackageImport.tsx         # 接收 ZIP、展示服务端预览并确认导入，完成后转入正式编辑器
└── SkillLibrarySync.tsx           # 显示后端来源目录，显式触发同步并反馈逐包成功、未变或冲突
```

## 与其他模块协作

技能读写归 [SkillStore](../../state/skills/skillStore.ts)，跨模块更新由 [WorkspaceData](../../state/README.md) 组合；API 客户端描述传输结构。后端 [skills](../../../../backend/app/skills/README.md) 校验并发布内容，[capability_catalog](../../../../backend/app/capability_catalog/README.md) 联合检索，[employees](../../../../backend/app/employees/README.md) 保存装配。MCP 配置由[工具页面](../tools/README.md)继续。

## 维护与验证

标准包、来源目录和运行字节的关系见[后端技能设计](../../../../backend/app/skills/README.md)，参数及公开字段见[配置契约](../../../../docs/reference/agent-configuration/api.md)。[编辑测试](SkillEditor.test.tsx)、[同步测试](SkillLibrarySync.test.tsx)及[配置流程测试](configurationFlow.test.tsx)核对完整加载、草稿和保存，不证明方法实际完成业务任务。
