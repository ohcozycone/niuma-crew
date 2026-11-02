# 共享组件盘点与完整封装

日期：2026-10-31。按用户明确选择“梳理后直接改组件，卡片样稿单独确认”实施；[增量范围](../proposals/component-encapsulation.md)。知识卡片后经用户确认并落地，当前复用员工同源卡片；本任务未改后端或业务数据。以下保留各次快照的结果和限制。

历史证据说明（2026-11-02 核对）：下文 `.impeccable/review/` 路径只保留原证据位置，相关文件当前工作区已缺失，无法据此重新核验当时结果；不将历史通过结果视为当前验收。

## 全量盘点覆盖了什么

对改造前198份非测试 TS/TSX/CSS 做静态扫描，登记102份共享/页面 TSX；改造完成时201份源文件、105份 TSX（基础UI21、共享层合计52、页面及私有组件53）；收尾重扫因并行向量功能增加到205份源文件、106份TSX（共享52、页面54），11份CSS/Styles文件。排除测试、生成物、头像SVG原画和模块图。外壳 Layout 与路由的消费关系也在扫描范围，不把目录名当作架构结论。

逐文件核对清单 CSV（原路径 `.impeccable/review/component-encapsulation/reviewed-inventory.csv`）、改造前引用（原路径 `.impeccable/review/component-encapsulation/usage-before.csv`）、改造后引用（原路径 `.impeccable/review/component-encapsulation/usage.csv`）支持复查。计数按模块族直接JSX导入，Card/Footer、Dialog各部件等不混称独立组件；目录转导出、动态路由单独辨认，零直接JSX引用不等于死代码。className次数只用来定位，不能直接当成缺陷数。静态全量覆盖不等于逐页面所有状态均做过浏览器验收。

## 发现与已经落地的改造

| 组合           | 确认问题                                                      | 当前处理                                                                                                 |
| -------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| 页面与面板Tab  | 员工目录、编辑器、知识页及样板分别补尺寸、边界和标签样式      | PageTabs统一列表、标签、计数、基线、指示线与响应；7个消费者迁移，原Tabs保留分段选择用途                  |
| 普通字段       | 反复写标签和控件间距，说明容易混进控件可访问名称              | 58处迁入FormField，统一标签/控件关联、说明/错误位置及aria；保留业务校验和表单值                          |
| 弹窗           | 8处中央弹窗手工补纵向滚动                                     | DialogContent中央模式默认滚动，side仍使用自身主体滚动；消费者无需补默认滚动                              |
| 账户入口与菜单 | 规范样板复制真实账户按钮；危险项局部重写颜色                  | AccountMenuButton同时承载身份内容及样式，两处共用；DropdownMenuItem提供destructive语义，分组标题自带样式 |
| 空态           | 4处消费者重写padding，尺寸随页面漂移                          | EmptyState提供default/compact密度，移除这些内部间距覆盖                                                  |
| 内嵌历史表面   | 页面通过class抹掉Card边框、底色、圆角                         | Card提供plain与none语义，调用方只选择用途                                                                |
| 页头动作       | 知识新建/添加、能力目录添加位于搜索工具栏；知识详情多一行返回 | 主操作进入PageHeading.actions；搜索刷新仍在集合附近，知识来源返回保留原问题路径                          |

已经具备完整默认样式的 Button、Input、SelectField、Badge、Switch、导航、Tooltip、消息/运行过程、主题和头像等不重做。Card内部排版、PageContainer外部空间、SearchInput在工具栏中的宽度是业务布局责任，不以“一律删除className”代替审查。

Field/Form是低层语义适配，仅品牌登录使用；普通页面不把这两个裸适配当成完整样式组件。登录、员工身份/模型选择、对话编辑器、头像检阅保留其已明确的业务造型和功能包装。原生按钮/label的存在不直接判错，例如头像选择、遮罩和开关标签各有不同交互任务。

## 防止后续再漂移

现行规范见[共享表面](../../frontend/src/design-system/surfaces.md)和[组件规范](../../frontend/src/design-system/components.md)，清单见[组件盘点](../../frontend/src/design-system/component-inventory.md)。普通页面用完整组合入口，只传数据/事件/内容和语义变体。新增通用变体先进入组件，示例直接消费正式组件，不能复制样式造一份假样板。

新增测试覆盖Tab与面板关联、计数可访问名称、字段标签/表单值/辅助信息及长弹窗滚动；源代码约束阻止页面给TabsHeader/List/Trigger重配样式、重复补弹窗默认滚动。它们只拦截明确的责任回退，不声称能自动判断全部设计质量。

## 11:22 至11:57验证与样稿快照

共享组件版本于11:22完成前端436项测试（61文件），ESLint、TypeScript和生产构建通过；构建保留既有大分块提示。并行功能随后新增的逻辑不包含在该测试时点。

Chrome实际核对1455px知识总览/详情、员工目录/面板与普通字段弹窗；390px核对页头换行、Tab整行基线、规则字段与手动键盘激活/URL切换。账户菜单开关和空白大脑弹窗取消通过，未保存或退出会话。窄屏知识列表当时API失败，一次重试仍失败；该截图只证明错误布局，不能作为正常窄屏列表验收。未覆盖Safari/Firefox、夜间主题本轮浏览器回归或全部105个文件的所有状态。零发现的静态检测也不证明视觉全面正确。本轮未改后端，不重报上轮后端测试为本轮结果。

独立审查发现8处帮助文字未完整接入字段description，已合批迁移并补真实MCP凭据消费者的说明关联回归。限定修复复核为ship，只覆盖F1清单，见初审（原路径 `.impeccable/review/component-encapsulation/finish-review.md`）与复核（原路径 `.impeccable/review/component-encapsulation/finish-verdict.md`）。11:57三文件9项定向测试及当时全前端ESLint通过；修复后TypeScript、生产构建通过。11:50并行代码快照的全量473项有470通过、3失败，涉及知识错误返回链接、MCP读取动作和网络错误文案；随后大脑页面发生结构/命名改造，旧大脑定向用例也未通过。不能把11:22的436通过当作最新全量通过。未在本轮改写并行功能的预期断言以获得绿灯。

make check-docs曾受默认uv缓存读取限制，使用现有Python运行同一检查脚本；首次发现并行新增检索方案缺少索引入口，已补链接，最终结果见检查输出。

在该时点，最初隔离CSS书本样稿、写实书本生图以及彩色文件夹生图均已撤回，均未接入正式页面。用户选择复用现成Card，使用统一通用知识图标并少量叠页装饰，内容靠名称和用途区分；当时的生图只展示两份实际演示库，尚待确认。样稿中的额外省略号不代表新增菜单能力，卡片尺寸仍须按既有网格预算实现。探索来源与提示词保留在当时方向记录（原路径 `.impeccable/review/component-encapsulation/latest-direction.md`）和提示词（原路径 `.impeccable/review/component-encapsulation/image-prompts.json`），后续确认和落地以本记录下一节为准。

## 12:15知识卡片确认、适配与验收

用户随后明确确认上一版通用图标卡片，并要求复用员工卡片样式后叠加设计细节，先前暂停已解除。批准参考为本机截图 `codex-clipboard-f2849c8c-f123-4409-ab6f-f5e94671fcac.png`；完整独立收尾审查（原路径 `.impeccable/review/knowledge-card-adaptation/finish-review.md`） 已读取该图。正式 KnowledgeCard 直接使用员工同源 Card 的默认 raised/card 表面和交互阴影，所有库统一使用 BookOpen、Bookmark 与轻微叠页。新 CardContent 从员工原内容容器提取标准留白，员工既有窄容器覆盖保留；二者共用 CardFooter。标题和用途各两行，底栏显示文档数/更新时间，整卡链接保留完整名称和标题提示，不实现无动作省略号。KnowledgeLibraries 只组合完整 KnowledgeCard，不再重写 outline/panel 表面和内部留白。

当前静态清单为114个非测试TSX：共享层57（含基础UI21）、页面及其私有展示57；新增登记并行大脑任务的 ModelConnections（C03/C12/C22）及 KnowledgeCard（C08）。原106个文件及205份源码统计仍是前述扫描快照，114也不代表全部状态经过浏览器运行。

12:15:26 启动的全前端测试为71文件、497项通过；该快照 ESLint、TypeScript 和生产构建通过，日志为 `/private/tmp/knowledge-card-{tests,lint,types,build}.log`，构建保留既有大于500kB分块提示。此结果是后续快照，不删除或改写11:50及随后定向失败的历史事实，也不以本次前端通过证明所有并行业务正确。

浏览器核对正式1412×702与390×844知识列表的3个真实库，点击项目技术文档进入真实库详情并返回通过；390px无横向溢出。员工与知识卡片计算样式均为0.5px外框、16px圆角、20px/20px/16px内容留白，知识卡片当时尺寸269×154.30px。隔离夹具覆盖长中文名、无空格英文、空说明、空库及12345文档数；320px无横向溢出，明暗色与整卡键盘焦点已查看。夹具直接消费正式组件，不调用API、不写业务数据、不更改用户主题。

截图位于 knowledge-card-adaptation（原路径 `.impeccable/review/knowledge-card-adaptation/desktop.jpg`） 同目录：desktop、mobile、agents、fixtures-desktop、fixtures-mobile、fixtures-dark-mobile、fixtures-dark-desktop 均为有效第一视口，不能称为长页完整截图。fresh reviewer 完整五节审查为 ship，范围限于本次卡片适配和共享内容容器；detector 一次扫描零发现。未覆盖Safari/Firefox、正式知识页夜间、全部状态/交互矩阵及员工卡片窄屏浏览器回归；本轮没有重验上传、权限、检索或后端链路。现行规则见设计系统和知识模块说明，文档收尾（原路径 `.impeccable/review/knowledge-card-adaptation/documentation-report.md`） 区分当前说明与历史证据。

## 通用图标试用与五个候选

用户随后要求使用生图模型重做图标，并明确要求替换查看。生成PNG已放入公开资源目录，KnowledgeCard改为48px透明底图片，保留现有Card与排版；来源和提示词维护在前端knowledge-assets.json。实际夜间桌面与390px效果保存在 `.impeccable/review/knowledge-icon-integration/`，3张图片均已加载且自然尺寸可读。该快照知识页面15项定向测试、ESLint、TypeScript和构建通过，不重报上一轮497项为本次结果。

用户看到页面后否定其偏立体的风格，要求更贴近数字员工的扁平搞笑形象，并生成5个候选。因此本次试用不记为视觉验收通过，原卡片结构的已确认状态仍保留。新候选使用数字员工扁平原画作参考，分别为眼镜书本、鼓鼓文件夹、摸鱼档案盒、歪歪书摞、牛角知识手册；5个PNG及完整提示词保存在 `frontend/output/knowledge-icon-study/candidates-v2/`，并排展示另含48px预览。候选未接入正式页面，采用哪一个仍待用户选择。

用户随后附2号文件夹截图并要求“试试”，已使用原透明PNG接入 `public/knowledge/library-folder.png`，避免把附件棋盘背景当作素材。只替换图标URL，48px占位与卡片布局保持既有实现。实际夜间桌面1412×758可见3个库均正常加载，图片自然宽1254、显示48×48；试用效果（原路径 `.impeccable/review/knowledge-folder-trial/desktop.jpg`）。该次知识页面15项定向测试、单文件ESLint与生产构建通过，构建保留既有大块提示；未重跑全量、类型或后端验证，也未重验日间/窄屏。当前为选中候选试用，尚不宣称用户已认可最终效果。

用户随后认可文件夹设计并要求“去掉眼镜”。现有候选只有拟人眼睛，按图中实际装饰去掉眼睛及眼袋，保留文件夹、纸张和回形针。内置image_gen编辑后的透明版本接入 `public/knowledge/library-folder-clean.png`，旧素材保留；元数据追加编辑提示词、原始输入与新输出的来源及摘要。实际夜间桌面3个图标已加载，48px留位与卡片布局保持既有值；去掉眼部后的效果（原路径 `.impeccable/review/knowledge-folder-clean/desktop.jpg`）。该次知识页15项定向测试、单文件ESLint和构建通过，未重报旧全量结果；当前验收限于本次素材替换。
