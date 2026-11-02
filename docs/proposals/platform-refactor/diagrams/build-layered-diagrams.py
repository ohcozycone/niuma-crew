"""Draw the reviewed architecture as four separate, annotated layered SVGs.

Panels express ownership, cards express responsibilities, and record names appear
only inside their owning module. Dashed future capabilities are not implemented.
"""

import unicodedata
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLORS = {
    "cyan": "#48c7ed",
    "green": "#63d5b2",
    "purple": "#b99bfa",
    "amber": "#f3c567",
    "rose": "#f29cae",
    "slate": "#a2b4cd",
}
BG = "#0c1423"
PANEL = "#101e30"
CARD = "#14263b"


def text_width(value, size):
    """Conservative layout estimate; final output is also visually inspected."""
    return sum(size * (1 if unicodedata.east_asian_width(char) in "WF" else 0.59) for char in value)


def wrapped(value, max_width, size):
    lines, line = [], ""
    for char in value:
        if line and text_width(line + char, size) > max_width:
            lines.append(line)
            line = char
        else:
            line += char
    if line:
        lines.append(line)
    return lines


class Diagram:
    def __init__(self, height, title, subtitle, number):
        self.width, self.height = 1800, height
        self.regions, self.edges, self.cards, self.labels = [], [], [], []
        self.number = number
        self.title = title
        self.subtitle = subtitle
        self.text(40, 62, title, 35, weight=700)
        self.text(40, 103, subtitle, 19, fill="#b6c6da")
        self.text(
            1760,
            140,
            f"{number} / 04  ·  当前实施 / 职责边界  ·  2026-10-27",
            16,
            fill="#a2b4cd",
            anchor="end",
        )

    def text(self, x, y, value, size=18, fill="#eaf1fa", weight=400, anchor="start"):
        assert 20 <= x <= 1780 and 20 <= y <= self.height - 20, value
        self.labels.append(
            f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{escape(value)}</text>'
        )

    def panel(self, x, y, w, h, title, subtitle, color="green", proposed=False):
        stroke = COLORS[color]
        dash = ' stroke-dasharray="10 6"' if proposed else ""
        self.regions.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" '
            f'fill="{PANEL}" stroke="{stroke}" stroke-width="1.7"{dash}/>'
        )
        self.regions.append(
            f'<path d="M{x + 18} {y + 1}H{x + w - 18}" '
            f'stroke="{stroke}" stroke-width="4" stroke-linecap="round"/>'
        )
        size = min(24, (w - 48) / max(text_width(title, 1), 1))
        self.text(x + 24, y + 34, title, size, stroke, 650)
        assert text_width(subtitle, 17) <= w - 48, subtitle
        self.text(x + 24, y + 64, subtitle, 17, "#aebfd4")

    def card(self, x, y, w, h, title, lines=(), code="", color="green", proposed=False):
        stroke = COLORS[color]
        dash = ' stroke-dasharray="7 5"' if proposed else ""
        self.cards.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" '
            f'fill="{CARD}" stroke="{stroke}" stroke-opacity="0.65"{dash}/>'
        )
        title_size = min(22, (w - 36) / max(text_width(title, 1), 1))
        assert title_size >= 17, title
        self.text(x + 18, y + 32, title, title_size, "#f2f6fc", 600)
        body_size = 17 if h < 110 else 18
        baseline = y + 61
        if code:
            code_size = min(15, (w - 36) / max(text_width(code, 1), 1))
            assert code_size >= 12, code
            self.text(x + 18, y + 55, code, code_size, stroke)
            baseline = y + 80
        for raw in lines:
            for line in wrapped(raw, w - 36, body_size):
                assert baseline <= y + h - 10, (title, line, baseline, y + h)
                self.text(x + 18, baseline, line, body_size, "#bacbde")
                baseline += 27 if body_size == 18 else 23

    def arrow(self, path, color="slate", dashed=False):
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        self.edges.append(
            f'<path d="{path}" fill="none" stroke="{COLORS[color]}" '
            f'stroke-width="2" marker-end="url(#arrow-{color})"{dash}/>'
        )

    def footer(self, first, second):
        y = self.height - 87
        self.regions.append(f'<path d="M40 {y - 22}H1760" stroke="#34445a" stroke-width="1"/>')
        self.text(40, y + 4, first, 17, "#b6c6da")
        self.text(40, y + 34, second, 17, "#a2b4cd")
        self.text(
            1760,
            self.height - 22,
            "NIUMACREW · LAYERED ARCHITECTURE",
            13,
            "#7b91ad",
            anchor="end",
        )

    def save(self, filename):
        markers = "".join(
            f'<marker id="arrow-{name}" markerWidth="9" markerHeight="8" '
            f'refX="8" refY="4" orient="auto"><path d="M0 0L9 4L0 8Z" '
            f'fill="{color}"/></marker>'
            for name, color in COLORS.items()
        )
        svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1800 {self.height}" '
            'role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(self.title)}</title>',
            f'<desc id="desc">{escape(self.subtitle)} 实线表示已有职责，虚线表示后续未实现能力；当前范围已实施。</desc>',
            f'<defs>{markers}<pattern id="grid" width="40" height="40" '
            'patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" '
            'stroke="#20314a" stroke-width="0.5"/></pattern><style>'
            "text{font-family:'PingFang SC','Noto Sans SC','Microsoft YaHei',sans-serif}"
            "</style></defs>",
            f'<rect width="1800" height="{self.height}" fill="{BG}"/>',
            f'<rect width="1800" height="{self.height}" fill="url(#grid)" opacity="0.35"/>',
            *self.regions,
            *self.edges,
            *self.cards,
            *self.labels,
            "</svg>",
        ]
        (HERE / filename).write_text("\n".join(svg) + "\n")


def overview():
    d = Diagram(
        1790,
        "全局架构｜先分职责层，再看模块归属",
        "主区自上而下区分界面、接口、业务协作和执行；侧栏单列横切、工程与未来能力。",
        "01",
    )
    d.panel(
        40,
        170,
        1260,
        200,
        "01  用户界面｜按页面与交互组织",
        "前端页面组合后端能力，不复制后端模块树。",
        "cyan",
    )
    for x, title, lines in [
        (64, "对话工作区", ("输入、回复、历史导航", "CI 诊断结果展示")),
        (375, "员工与资源", ("员工、方法、模型连接", "规章制度与资料入口")),
        (686, "身份与设置", ("登录、当前身份", "主题与表单交互")),
        (997, "帮助与展示", ("帮助、设计系统", "头像与品牌资源")),
    ]:
        d.card(x, 252, 279, 94, title, lines, color="cyan")

    d.panel(
        40,
        410,
        1260,
        190,
        "02  对外接口｜表达客户端需要的操作",
        "以对话、配置、身份等场景提供契约；不强制采用 Thread / Turn 路径。",
        "cyan",
    )
    for x, title, line in [
        (64, "对话操作", "发送、重试、停止"),
        (375, "历史与观察", "分页、定位、持续更新"),
        (686, "配置管理", "读取、编辑、修订校验"),
        (997, "身份与公开信息", "登录、退出、公开摘要"),
    ]:
        d.card(x, 492, 279, 84, title, (line,), color="cyan")

    d.panel(
        40,
        640,
        1260,
        210,
        "03  请求与共享流程｜职责分区，不新增全局目录",
        "请求服务归 API；准备、授权和发布归 conversations；简单配置调所属服务。",
        "purple",
    )
    for x, title, lines in [
        (64, "API 请求服务", ("请求键、目标与接受事务", "发送、停止、重试和反馈")),
        (478, "共享准备与授权", ("conversations 内明确函数", "API 与后台各时点复用")),
        (
            892,
            "共享发布与读取",
            ("完成、恢复和排队停止共用", "内容与终态在一个事务提交"),
        ),
    ]:
        d.card(x, 722, 384, 104, title, lines, color="purple")

    d.panel(
        40,
        890,
        1260,
        290,
        "04  后台职责｜业务所有者与执行支撑并列",
        "模块管理自己的数据与规则；下列卡片不是四个依次调用的步骤。",
        "green",
    )
    for x, title, code, lines in [
        (
            64,
            "对话与消息",
            "conversations",
            ("内容、顺序与历史", "原始提问与处理关联", "Message 是内部记录"),
        ),
        (
            375,
            "员工与资源配置",
            "agents / skills / rules",
            ("员工装配、共享方法", "模型连接与凭证修订", "配置生成本次执行依据"),
        ),
        (
            686,
            "专业诊断",
            "ci_diagnosis",
            ("构建目标与证据", "报告校验、读取、反馈", "专业规则不进入调度器"),
        ),
        (
            997,
            "执行管理",
            "execution",
            ("排队、取消与超时", "预算、过程与恢复", "Run 是内部执行记录"),
        ),
    ]:
        d.card(x, 978, 279, 176, title, lines, code, color="green")

    d.panel(
        40,
        1220,
        1260,
        210,
        "05  Agent 与外部能力｜执行过程的具体实现",
        "由执行宿主调用或受控接入；不是所有业务模块都必须经过这一层。",
        "green",
    )
    d.card(
        64,
        1302,
        384,
        104,
        "Agent 内部运行｜已独立",
        ("模型与工具循环、SDK 内容转换", "方法加载与 SDK 恢复解释"),
        color="green",
    )
    d.card(
        478,
        1302,
        384,
        104,
        "模型访问 · llm",
        ("模型工厂、受管网络", "协议错误与用量归一"),
        color="green",
    )
    d.card(
        892,
        1302,
        384,
        104,
        "现有工具与专业取证",
        ("CI 读取与 MCP 适配", "通用工具网关属于后续增量"),
        color="green",
    )

    d.panel(
        40,
        1470,
        1260,
        190,
        "06  技术设施｜由需要它的模块使用",
        "这是共享技术依赖区，不是请求必须经过的最后一个业务步骤。",
        "slate",
    )
    for x, title, line in [
        (64, "数据库与事务", "SQLite / SQLAlchemy / 正式迁移"),
        (478, "运行恢复存储", "SDK 存档与业务历史分开"),
        (892, "技术公共能力", "网络、加密机制、文件与错误识别"),
    ]:
        d.card(x, 1552, 384, 84, title, (line,), color="slate")

    d.panel(1340, 170, 420, 390, "横切能力", "多个入口使用；不表示独立业务步骤。", "rose")
    d.card(
        1364,
        252,
        372,
        120,
        "身份与权限 · auth",
        ("用户、登录会话、Actor", "角色能力与资源访问规则"),
        color="rose",
    )
    d.card(
        1364,
        412,
        372,
        120,
        "HTTP 与公开边界",
        ("来源校验、限流、错误转换", "公开字段与敏感信息隔离"),
        color="rose",
    )
    d.panel(
        1340,
        600,
        420,
        540,
        "装配、交付与工程",
        "是另一种视角，不属于业务调用层级。",
        "amber",
    )
    d.card(
        1364,
        682,
        372,
        130,
        "启动装配",
        (
            "main / bootstrap / config",
            "创建具体依赖并管理启停",
            "不拥有业务状态和授权规则",
        ),
        color="amber",
    )
    d.card(
        1364,
        852,
        372,
        110,
        "当前部署",
        ("FastAPI 同源静态交付", "SQLite、单执行宿主、进程锁"),
        color="amber",
    )
    d.card(
        1364,
        1002,
        372,
        110,
        "开发与验证",
        ("Makefile、scripts、构建与测试", "docs、日志与维护入口"),
        color="amber",
    )
    d.panel(
        1340,
        1180,
        420,
        480,
        "后续独立能力｜未实现",
        "单独规划，不塞入本次核心调用链。",
        "slate",
        proposed=True,
    )
    d.card(
        1364,
        1262,
        372,
        84,
        "通用工具｜后续",
        ("连接、目录、授权与受控调用",),
        color="slate",
        proposed=True,
    )
    d.card(
        1364,
        1386,
        372,
        84,
        "真实知识能力｜后续",
        ("导入、发布、检索与引用",),
        color="slate",
        proposed=True,
    )
    d.card(
        1364,
        1510,
        372,
        124,
        "按需工作能力｜后续",
        ("任务、计划、目标、定时触发", "模式和跨轮控制分别设计"),
        color="slate",
        proposed=True,
    )
    for a, b in [(370, 410), (600, 640), (850, 890)]:
        d.arrow(f"M670 {a}V{b}")
    d.footer(
        "读图：大框 = 职责分区；小框 = 模块或能力；记录名称只写在所属模块内部。",
        "实线 = 当前实现；虚线 = 后续能力。具体协议与验证范围见现行契约和实施记录。",
    )
    d.save("layered-01-overview.svg")


def frontend():
    d = Diagram(
        1620,
        "前端分层｜围绕页面、交互和状态组织",
        "Hook 面向组件使用方式，API 面向稳定操作；两者都不要求与后端实体或文件一一对应。",
        "02",
    )
    d.panel(
        40,
        170,
        1260,
        205,
        "01  页面入口｜用户在哪个工作界面",
        "路由、Layout 与页面负责界面组合；下面保留当前产品名称。",
        "cyan",
    )
    for x, title, code, line in [
        (64, "对话", "pages/conversations", "输入、回复、过程、历史"),
        (375, "员工与方法", "pages/agents · skills", "资源管理与工作入口"),
        (686, "模型与资料", "pages/brains · knowledge", "模型连接、规则与资料"),
        (997, "登录及辅助页面", "signin · help · avatars", "另含 design-system 展示"),
    ]:
        d.card(x, 252, 279, 99, title, (line,), code, color="cyan")
    d.panel(
        40,
        415,
        1260,
        270,
        "02  页面功能｜按用户交互拆分",
        "一个功能可以组合消息、执行状态、员工摘要和报告等多种后端数据。",
        "cyan",
    )
    d.card(
        64,
        497,
        384,
        160,
        "对话交互",
        (
            "输入与提交、停止与重试",
            "回复正文、生成过程和错误",
            "历史窗口、问题目录与定位",
        ),
        color="cyan",
    )
    d.card(
        478,
        497,
        384,
        160,
        "配置编辑",
        ("表单字段与方法选择", "草稿、修订冲突与导航保护", "资源摘要及保存反馈"),
        color="cyan",
    )
    d.card(
        892,
        497,
        384,
        160,
        "身份与导航",
        ("登录、退出与角色展示", "页面切换、来源返回", "主题选择与帮助入口"),
        color="cyan",
    )
    d.panel(
        40,
        725,
        1260,
        270,
        "03  页面接入与状态｜Hook、控制器、局部仓库",
        "按真实复用和生命周期决定拆分；停止操作仍须准确指向那次处理。",
        "purple",
    )
    d.card(
        64,
        807,
        384,
        160,
        "命令与网络协调",
        (
            "提交、重试、停止和待确认恢复",
            "切换页面后的请求取消与失效保护",
            "useConversationController 等",
        ),
        color="purple",
    )
    d.card(
        478,
        807,
        384,
        160,
        "组件读取 Hook",
        (
            "useConversation 读取页面所需内容",
            "回复可组合正文、状态和操作",
            "useMessage 读取这一行及操作",
        ),
        color="purple",
    )
    d.card(
        892,
        807,
        384,
        160,
        "局部状态与观察",
        (
            "Provider / store / reducer 分工",
            "历史窗口与稳定对象快照",
            "同一处理只维护必要的单条订阅",
        ),
        color="purple",
    )
    d.panel(
        40,
        1035,
        1260,
        220,
        "04  数据访问｜对接 HTTP 契约",
        "页面使用场景接口；内部再映射字段和组合请求，不泄露数据库结构。",
        "green",
    )
    d.card(
        64,
        1117,
        384,
        112,
        "HTTP 客户端 · lib/api",
        ("请求、响应类型与错误解析", "对话、配置、身份等场景操作"),
        color="green",
    )
    d.card(
        478,
        1117,
        384,
        112,
        "可注入 transport",
        ("为页面提供需要的网络能力", "测试替身与真实连接使用同一边界"),
        color="green",
    )
    d.card(
        892,
        1117,
        384,
        112,
        "持续更新接入",
        ("SSE、版本去重、只读重连", "订阅不是启动或取消处理的命令"),
        color="green",
    )
    d.panel(
        40,
        1295,
        1260,
        190,
        "共享界面依赖｜可被多个上层使用",
        "这是复用区域，不表示 HTTP 客户端需要依次调用下面的组件。",
        "slate",
    )
    for x, title, line in [
        (64, "基础控件与通用展示", "components/ui · common"),
        (375, "业务复用组件", "员工、方法、身份与配置表单"),
        (686, "设计系统", "主题令牌、样式与交互约定"),
        (997, "头像与品牌", "成品资源、清单与构建脚本"),
    ]:
        d.card(x, 1377, 279, 84, title, (line,), color="slate")
    d.panel(
        1340,
        170,
        420,
        320,
        "共享身份状态",
        "跨页面存在；由后端确认身份与权限。",
        "rose",
    )
    d.card(
        1364,
        252,
        372,
        210,
        "state/auth",
        (
            "保存当前身份和作用域",
            "身份变化时清理旧请求与观察",
            "前端按钮可见性不替代权限检查",
            "不持有对话正文或执行调度规则",
        ),
        color="rose",
    )
    d.panel(
        1340,
        530,
        420,
        320,
        "共享编辑状态",
        "页面持有资源；外壳管理离开保护。",
        "purple",
    )
    d.card(
        1364,
        612,
        372,
        210,
        "state/configuration · editing",
        (
            "配置只通知更新；草稿留页面",
            "编辑区注册放弃回调与保存锁",
            "useDraft / useQueryState 等辅助",
            "不接管对话提交与流式订阅",
        ),
        color="purple",
    )
    d.panel(
        1340,
        890,
        420,
        320,
        "主题、外壳与通用能力",
        "作为共享依赖使用，不形成业务实体。",
        "amber",
    )
    d.card(
        1364,
        972,
        372,
        210,
        "state/theme · router · lib",
        (
            "主题初始化与持久选择",
            "Layout、返回路径和页面懒加载",
            "通用格式与浏览器工具",
            "共享组件不导入页面私有状态",
        ),
        color="amber",
    )
    d.panel(
        1340,
        1250,
        420,
        235,
        "前后端必须对齐的含义",
        "结构与命名可以不同，行为不能歧义。",
        "green",
    )
    d.card(
        1364,
        1332,
        372,
        125,
        "稳定标识与操作约定",
        ("状态、ID、分页、错误及权限范围", "取消和重试准确指向指定处理"),
        color="green",
    )
    for a, b in [(375, 415), (685, 725), (995, 1035)]:
        d.arrow(f"M670 {a}V{b}")
    d.footer(
        "Hook 的边界取决于组件交互；API 的边界取决于稳定用户操作；后端模块的边界取决于数据与规则所有权。",
        "不强制 useTurn、不强制改 /api/threads；现有请求保护、历史定位和单订阅行为需要保留。",
    )
    d.save("layered-02-frontend.svg")


def backend():
    d = Diagram(
        1780,
        "后端分层｜业务协作、数据所有者与运行支撑",
        "请求 service 可在 API；共享流程归业务模块；execution 只接受注入的运行协作能力。",
        "03",
    )
    d.panel(
        40,
        170,
        1260,
        200,
        "01  HTTP 适配 · api",
        "解析请求、响应与身份；接口围绕客户端业务操作组织。",
        "cyan",
    )
    for x, title, line in [
        (64, "对话与诊断入口", "发送、读取、停止、报告与反馈"),
        (375, "配置与资源入口", "员工、方法、模型、规则与摘要"),
        (686, "身份及公开入口", "登录、OAuth、公开数据与健康"),
        (997, "传输公共机制", "来源校验、限流与错误转换"),
    ]:
        d.card(x, 252, 279, 94, title, (line,), color="cyan")
    d.panel(
        40,
        410,
        1260,
        240,
        "02  请求编排与共享流程 · 按所属模块组织",
        "此处是职责分区：请求服务归 API，三项共享流程归 conversations；不建 application/use_cases。",
        "purple",
    )
    d.card(
        64,
        492,
        384,
        134,
        "接受与控制 · API",
        ("创建对话、提交、重试和停止", "内容、执行记录与关联一起提交"),
        "api/.../conversations/service.py",
        "purple",
    )
    d.card(
        478,
        492,
        384,
        134,
        "共享结果发布",
        ("调用业务发布器与执行收尾", "答复、终态和关联一起提交"),
        "conversations/publication.py",
        "purple",
    )
    d.card(
        892,
        492,
        384,
        134,
        "共享准备与授权",
        ("preparation / authorization", "启动、动作、恢复与发布共用"),
        color="purple",
    )
    d.panel(
        40,
        690,
        820,
        440,
        "03A  业务模块｜各自拥有数据与规则",
        "内部可含模型、读取和写入；不为每个对象新建一个模块。",
        "green",
    )
    business = [
        (64, 772, "对话与消息", "conversations", "内容、顺序、历史和处理关联"),
        (465, 772, "数字员工", "agents", "员工配置、装配与执行配置视图"),
        (64, 892, "共享方法", "skills", "方法定义、参数与资源规范"),
        (465, 892, "模型连接", "model_connections", "模型配置、凭证生命周期与修订"),
        (64, 1012, "全员规则", "organization_rules", "规则内容及版本化替换"),
        (465, 1012, "专业诊断", "ci_diagnosis", "目标、证据、报告校验和反馈"),
    ]
    for x, y, title, code, line in business:
        d.card(x, y, 371, 94, title, (line,), code, color="green")
    d.panel(
        900,
        690,
        400,
        440,
        "03B  执行支撑 · execution",
        "只用注入回调，不反向导入 API。",
        "green",
    )
    d.card(
        924,
        772,
        352,
        140,
        "执行数据与本地规则",
        (
            "执行记录 Run、实际动作与用量",
            "状态转换、预算和进度存取",
            "正文与专业报告归业务模块",
        ),
        color="green",
    )
    d.card(
        924,
        952,
        352,
        150,
        "准入与运行控制",
        (
            "幂等、容量与排队",
            "调度、取消、超时、恢复与收尾",
            "不创建聊天消息或解释诊断报告",
        ),
        color="green",
    )
    d.panel(
        40,
        1170,
        1260,
        240,
        "04  运行与协议实现｜由执行支撑调用具体实现",
        "运行时获得冻结输入和受限能力；不反向读取业务 ORM 或决定业务发布。",
        "green",
    )
    d.card(
        64,
        1252,
        384,
        130,
        "Agent 内部运行｜已独立",
        ("从 execution/sdk 等职责迁出", "SDK 循环、流处理与恢复格式"),
        "agent_runtime",
        "green",
    )
    d.card(
        478,
        1252,
        384,
        130,
        "模型访问",
        ("模型工厂、网络资源与协议适配", "错误分类与用量解析"),
        "llm",
        "green",
    )
    d.card(
        892,
        1252,
        384,
        130,
        "外部工具适配",
        ("当前 CI 取证与 MCP 接入", "通用 tools 网关另列后续增量"),
        "ci_diagnosis / MCP",
        "green",
    )
    d.panel(
        40,
        1450,
        1260,
        190,
        "技术设施｜数据库与公共技术机制",
        "模块按需使用；表结构、事务工具和运行恢复有各自的维护入口。",
        "slate",
    )
    for x, title, line in [
        (64, "infrastructure/database", "连接、事务、字段、错误识别与注册"),
        (478, "正式迁移与恢复存档", "稳定业务数据与 SDK 状态分开"),
        (892, "共享错误与技术机制", "errors / schemas / 网络 / 加密"),
    ]:
        d.card(x, 1532, 384, 84, title, (line,), color="slate")
    d.panel(
        1340,
        170,
        420,
        290,
        "身份与权限所有者 · auth",
        "是业务能力；被多个层的入口使用。",
        "rose",
    )
    d.card(
        1364,
        252,
        372,
        180,
        "身份生命周期与访问规则",
        (
            "用户、外部身份、登录会话",
            "Actor、角色能力与资源策略",
            "运行期间仍需通过受限接口复核",
            "规则不复制到执行器和前端",
        ),
        color="rose",
    )
    d.panel(
        1340,
        500,
        420,
        350,
        "装配与进程生命周期",
        "能认识具体实现，不拥有业务规则。",
        "amber",
    )
    d.card(
        1364,
        582,
        372,
        240,
        "main / bootstrap / config",
        (
            "main 导出 ASGI 入口",
            "bootstrap 创建并连接实际依赖",
            "config 读取和组合配置",
            "启动、关闭、进程锁和资源释放",
            "frontend_delivery 负责静态交付",
        ),
        color="amber",
    )
    d.panel(
        1340,
        890,
        420,
        300,
        "跨模块协作约束",
        "按完整操作组织；数据仍各自拥有。",
        "purple",
    )
    d.card(
        1364,
        972,
        372,
        190,
        "清楚的依赖方向",
        (
            "请求或共享流程组合明确操作",
            "执行模块调用受限运行接口",
            "运行时不读取 auth 或对话表",
            "模型与工具等待在业务事务外",
        ),
        color="purple",
    )
    d.panel(
        1340,
        1230,
        420,
        410,
        "记录归属｜不是新增调用层",
        "实体写在所属模块内部，避免与模块混排。",
        "slate",
    )
    d.card(
        1364,
        1312,
        372,
        300,
        "内容与处理分开记录",
        (
            "Conversation / Message：对话模块",
            "Run / Action：执行模块",
            "请求服务建立关联并检查归属",
            "Message 不需要独立服务模块",
            "具体正文迁移见数据方案",
            "不增加同生命周期的两层执行",
            "读取组合不是新增领域实体",
        ),
        color="slate",
    )
    d.arrow("M670 370V410")
    d.arrow("M450 650V690")
    d.arrow("M1100 650V690")
    d.arrow("M1100 1130V1150H256V1170")
    d.footer(
        "请求服务组织请求事务；共享准备授权发布归对话；execution 管运行，后台不导入 API。",
        "仍是模块化单体；图中区域不表示微服务、独立数据库或新增部署单元。",
    )
    d.save("layered-03-backend.svg")


def runtime():
    d = Diagram(
        1750,
        "执行边界｜宿主管运行，Agent 管内部模型与工具循环",
        "execution 是模块；Run 是模块内的执行记录。Agent 不通过共享对象取得整个数据库或执行存储。",
        "04",
    )
    d.panel(
        40,
        170,
        1720,
        205,
        "API 请求服务与对话共享流程｜各自归属，明确调用",
        "接受归 API 请求服务；准备、授权和发布归 conversations；Agent 返回候选，宿主调用共享发布。",
        "purple",
    )
    d.card(
        64,
        252,
        536,
        99,
        "接受操作",
        ("api/routes/conversations/service", "接受后由执行宿主独立调度"),
        color="purple",
    )
    d.card(
        630,
        252,
        536,
        99,
        "组合运行许可",
        ("conversations/authorization", "身份、装配与能力由所属模块检查"),
        color="purple",
    )
    d.card(
        1196,
        252,
        540,
        99,
        "发布操作",
        ("conversations/publication", "内容、专业报告与执行终态一起提交"),
        color="purple",
    )
    d.panel(
        40,
        430,
        720,
        920,
        "执行宿主 · execution",
        "管理一次处理的可靠运行；不实现模型与工具的决策循环。",
        "green",
    )
    host_cards = [
        (
            64,
            518,
            "执行记录",
            "记录 / 本地状态规则",
            (
                "Run：ID、输入依据和状态",
                "动作与运行状态归本模块",
                "正文和专业报告由业务保存",
            ),
            False,
        ),
        (
            415,
            518,
            "多次处理的调度",
            "scheduler（职责名）",
            (
                "扫描已接受的排队记录",
                "并发、进程锁和任务看护",
                "不替模型决定调用什么工具",
            ),
            False,
        ),
        (
            64,
            756,
            "单次处理控制",
            "coordinator",
            ("启动具体执行实现", "总时限、取消和故障收束", "调用注入的对话发布入口"),
            False,
        ),
        (
            415,
            756,
            "过程与预算存取",
            "store / control",
            (
                "记录实际动作、用量与进度",
                "持久预算跨恢复继续生效",
                "不解析 SDK 的 Message 类型",
            ),
            False,
        ),
        (
            64,
            994,
            "受限宿主接口",
            "RuntimeControl / control",
            (
                "检查是否允许继续",
                "确认动作、接收普通内容更新",
                "不公开存储、数据库与身份服务",
            ),
            False,
        ),
        (
            415,
            994,
            "恢复管理",
            "恢复引用 / 版本 / 预算",
            (
                "判断这次处理是否允许恢复",
                "保存恢复位置与兼容标识",
                "不解释具体 SDK 图节点",
            ),
            False,
        ),
    ]
    for x, y, title, code, lines, proposed in host_cards:
        d.card(x, y, 321, 198, title, lines, code, "green", proposed)
    d.text(64, 1250, "不负责：聊天内容规则、员工装配规则、专业报告解释。", 18, "#9fdcc8")
    d.text(
        64,
        1290,
        "SDK 解析、业务规则与执行控制各自维护，通过受限接口协作。",
        17,
        "#aebfd4",
    )

    d.panel(
        1000,
        430,
        760,
        920,
        "Agent 内部运行 · agent_runtime",
        "已从执行宿主拆出；内部使用 LangChain，宿主不解析 SDK 消息。",
        "cyan",
    )
    engine_cards = [
        (
            1024,
            518,
            "执行实现",
            "langchain.py / 启动",
            (
                "接收本次冻结输入和能力",
                "不自行查询用户或员工配置",
                "不创建应用的执行记录",
            ),
        ),
        (
            1391,
            518,
            "模型与工具循环",
            "langchain.py / 循环",
            (
                "调用模型、解释工具请求",
                "读取获准工具返回后继续",
                "决定内部循环何时结束",
            ),
        ),
        (
            1024,
            756,
            "SDK 内容转换",
            "streaming",
            (
                "区分模型文本和工具返回",
                "转换成普通内容更新",
                "不把每条 SDK message 当聊天",
            ),
        ),
        (
            1391,
            756,
            "本轮方法与工具",
            "skill_loading / middleware",
            ("装载本轮已获准资源", "通过宿主接口申请动作", "不扩展自身权限和预算"),
        ),
        (
            1024,
            994,
            "SDK 恢复解释",
            "checkpoints",
            ("解释具体 SDK 存档格式", "通过专用恢复端口读写", "不读取业务 Message 表"),
        ),
        (
            1391,
            994,
            "完成与产出",
            "运行返回值 / 失败类型",
            (
                "确认完整输出或明确失败",
                "返回文字、结构化结果与用量",
                "不提交业务终态或发布消息",
            ),
        ),
    ]
    for x, y, title, code, lines in engine_cards:
        d.card(x, y, 337, 198, title, lines, code, "cyan")
    d.text(
        1024,
        1250,
        "不持有：HTTP Request、Actor、业务 ORM、完整执行 Store。",
        18,
        "#a8dcf0",
    )
    d.text(1024, 1290, "SDK 类型停留在适配器；进度与结束信号使用普通数据。", 17, "#aebfd4")

    d.arrow("M400 375V430", "purple")
    d.text(424, 411, "接受后独立运行", 17, "#c6b3ef")
    d.arrow("M760 620H1000", "cyan")
    d.text(880, 599, "执行请求", 19, "#a8dcf0", anchor="middle")
    d.text(880, 652, "冻结输入 + 受限能力", 15, "#aebfd4", anchor="middle")
    d.arrow("M1000 860H760", "green")
    d.text(880, 839, "许可与过程更新", 19, "#9fdcc8", anchor="middle")
    d.text(880, 892, "确认后才发起动作", 15, "#aebfd4", anchor="middle")
    d.arrow("M1000 1100H760", "purple", dashed=True)
    d.text(880, 1079, "产出或失败", 19, "#c6b3ef", anchor="middle")
    d.text(880, 1132, "调用注入的对话 publication", 15, "#aebfd4", anchor="middle")

    d.panel(
        40,
        1390,
        1720,
        210,
        "由受限接口接入的能力｜不是运行时可以任意访问的共享对象",
        "下面是依赖和适配方向，不表示四项都由同一个模块拥有。",
        "slate",
    )
    for x, title, lines in [
        (
            64,
            "身份与配置规则",
            ("auth / agents / model_connections", "由应用授权逻辑组合"),
        ),
        (490, "模型与外部协议", ("llm、当前工具适配", "调用在业务事务外进行")),
        (916, "业务执行存储", ("由 execution 管理写入", "运行时只报告受限过程数据")),
        (1342, "SDK 恢复存储", ("专用恢复端口与格式适配", "已发布历史不依赖 SDK 存档")),
    ]:
        d.card(x, 1472, 394, 104, title, lines, color="slate")
    d.footer(
        "请求服务接受操作；对话共享流程准备授权发布；execution 管运行，agent_runtime 管内部循环。",
        "实体不构成调用层：Message 属于对话，Run 属于执行；受限控制与 SDK 目录已独立。",
    )
    d.save("layered-04-execution.svg")


if __name__ == "__main__":
    overview()
    frontend()
    backend()
    runtime()
    print("Generated 4 reviewed layered architecture SVGs.")
