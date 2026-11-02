"""Render the three explanatory views of the 2026-10-26 dependency review.

These are reviewed, selected relationships, not an automatically complete import graph.
The accompanying review records the source snapshot, evidence and omitted edges.
"""

from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BG = "#0f172a"
WHITE = "#e2e8f0"
MUTED = "#94a3b8"
BLUE = "#60a5fa"
CYAN = "#22d3ee"
GREEN = "#34d399"
PURPLE = "#a78bfa"
AMBER = "#fbbf24"
RED = "#fb7185"


class Diagram:
    def __init__(self, width, height, title, subtitle, kind):
        self.width, self.height = width, height
        self.shapes, self.lines, self.labels = [], [], []
        self.title, self.subtitle, self.kind = title, subtitle, kind

    def text(self, x, y, value, size=21, color=WHITE, anchor="start", weight=400):
        self.labels.append(
            f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
            f'text-anchor="{anchor}" font-weight="{weight}">{escape(value)}</text>'
        )

    def box(self, x, y, width, height, title, details=(), color=BLUE):
        self.shapes.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="{BG}"/>'
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" '
            f'fill="{color}" fill-opacity=".09" stroke="{color}" stroke-width="1.6"/>'
        )
        self.text(x + 20, y + 36, title, 25, color, weight=650)
        for index, line in enumerate(details):
            self.text(x + 20, y + 70 + index * 29, line, 20, MUTED)

    def region(self, x, y, width, height, label, color=MUTED):
        self.shapes.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="14" '
            f'fill="none" stroke="{color}" stroke-opacity=".5" stroke-dasharray="8 6"/>'
        )
        self.text(x + 16, y + 28, label, 19, color)

    def arrow(self, points, color=BLUE, dashed=False):
        path = "M " + " L ".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="8 6"' if dashed else ""
        self.lines.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.2"'
            f'{dash} marker-end="url(#a{color[1:]})"/>'
        )

    def save(self, name):
        markers = "".join(
            f'<marker id="a{c[1:]}" markerWidth="10" markerHeight="8" '
            f'refX="9" refY="4" orient="auto"><path d="M0 0 L10 4 L0 8" fill="{c}"/></marker>'
            for c in (BLUE, CYAN, GREEN, PURPLE, AMBER, RED, MUTED)
        )
        header = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'role="img" aria-labelledby="title desc"><title id="title">{escape(self.title)}</title>'
            f'<desc id="desc">{escape(self.subtitle)}</desc><defs>{markers}</defs>'
            '<style>text{font-family:"PingFang SC","Noto Sans SC",system-ui,sans-serif;}</style>'
            f'<rect width="100%" height="100%" fill="{BG}"/>'
        )
        self.text(50, 65, self.title, 36, weight=700)
        self.text(50, 108, self.subtitle, 22, MUTED)
        self.text(
            self.width - 50,
            self.height - 25,
            f"NIUMACREW · {self.kind} · 2026-10-26",
            17,
            MUTED,
            "end",
        )
        content = header + "".join(self.lines + self.shapes + self.labels) + "</svg>"
        (ROOT / f"{name}.svg").write_text(content)


def dependencies():
    d = Diagram(
        1600,
        1430,
        "源码依赖审查｜执行核心已分开，CI 特例仍向外扩散",
        "箭头：引用方 → 被引用方。展示关键跨模块 import；不把注入调用、SQL 与 import 混为一条线。",
        "CURRENT · SELECTED IMPORTS",
    )
    d.box(
        560, 180, 480, 105, "use_cases · 跨模块操作", ["组合接受 / 取消 / 重试 / 原子发布"], PURPLE
    )
    d.box(
        70, 405, 420, 120, "conversations · 对话与消息", ["业务消息 / 上下文 / 聊天读取投影"], CYAN
    )
    d.box(590, 405, 420, 120, "agents · 员工与装配", ["配置 / 装配 / 本次执行依据组合"], GREEN)
    d.box(1110, 405, 420, 120, "execution · 生命周期", ["Run / 动作 / 结果 / 调度 / 恢复"], AMBER)
    d.box(70, 720, 420, 120, "skills · 方法资产", ["方法与参数 / 捕获 / 当前装配许可"], GREEN)
    d.box(590, 720, 420, 120, "ci_diagnosis · 专业能力", ["仓库范围 / 专用循环 / 证据与报告"], RED)
    d.box(1110, 720, 420, 120, "model_connections", ["连接 / 凭证 / 修订 / 引用保护"], GREEN)
    d.box(70, 1030, 420, 105, "organization_rules", ["统一规则 / 提示词组合"], GREEN)
    d.box(590, 1030, 420, 105, "auth · 身份与访问控制", ["Actor / 登录会话 / 操作及资源许可"], CYAN)
    d.box(1110, 1030, 420, 105, "llm · 模型协议适配", ["模型工厂 / 网络资源 / 错误 / 用量"], BLUE)

    for points in (
        [(560, 230), (280, 230), (280, 405)],
        [(800, 285), (800, 405)],
        [(1040, 230), (1320, 230), (1320, 405)],
        [(490, 445), (590, 445)],
        [(590, 490), (490, 490)],
        [(650, 525), (340, 720)],
        [(400, 720), (700, 525)],
        [(1010, 445), (1110, 445)],
        [(1010, 490), (1180, 720)],
        [(1250, 720), (1250, 525)],
        [(1160, 720), (1010, 515)],
        [(900, 720), (900, 525)],
        [(590, 815), (490, 815)],
        [(1010, 750), (1170, 525)],
        [(1010, 815), (1280, 1030)],
        [(1140, 525), (1060, 610), (1060, 930), (800, 930), (800, 1030)],
        [(1530, 465), (1565, 465), (1565, 1080), (1530, 1080)],
        [(610, 525), (535, 570), (35, 570), (35, 1080), (70, 1080)],
    ):
        d.arrow(points, BLUE)
    d.arrow([(800, 525), (800, 720)], RED)
    d.arrow([(490, 780), (590, 780)], RED)
    d.arrow([(490, 515), (675, 720)], RED)
    d.text(820, 620, "CI 标识 / 特例", 19, RED)
    d.text(500, 432, "查询", 16, MUTED)
    d.text(500, 515, "保护", 16, MUTED)
    d.text(1290, 638, "活动引用检查", 18, MUTED)
    d.text(1170, 915, "模型调用", 18, MUTED)
    d.text(49, 965, "规则组合", 17, MUTED)

    d.box(
        70,
        1205,
        1460,
        135,
        "如何理解这些依赖",
        [
            "蓝线：类型、规则或查询依赖，是否合理需看用途；红线：通用模块直接认识 CI 专业标识。",
            "99 个 Python 文件 / 326 条内部导入 / 文件级无 import 环；5 个业务模块形成模块级互相依赖。",
        ],
        MUTED,
    )
    d.text(
        70,
        1380,
        "省略：API 到服务、bootstrap 装配、共用 DB/错误/DTO，以及部分授权边；详见报告与调度图。",
        20,
        MUTED,
    )
    d.save("current-dependencies")


def scheduling():
    d = Diagram(
        1800,
        1700,
        "运行时调度｜一次输入怎样成为已发布结果",
        "时间向下；实线为调用或写入，虚线为返回。HTTP 提交、后台执行、结果发布和只读观察分开。",
        "CURRENT · RUNTIME",
    )
    actors = [
        (120, "客户端 / HTTP", CYAN),
        (380, "提交用例", PURPLE),
        (640, "业务数据库", GREEN),
        (900, "Runner / 协调器", AMBER),
        (1160, "Agent 或 CI", BLUE),
        (1420, "发布用例", PURPLE),
        (1680, "SDK 恢复库", MUTED),
    ]
    for x, label, color in actors:
        d.box(x - 105, 175, 210, 70, label, color=color)
        d.lines.append(
            f'<path d="M{x} 245 V1530" stroke="#334155" stroke-width="2" stroke-dasharray="7 6"/>'
        )
    activations = (
        (380, 295, 495, PURPLE),
        (900, 590, 1180, AMBER),
        (1160, 785, 1080, BLUE),
        (1420, 1180, 1340, PURPLE),
    )
    for x, start, end, color in activations:
        d.shapes.append(
            f'<rect x="{x - 5}" y="{start}" width="10" height="{end - start}" '
            f'fill="{BG}" stroke="{color}"/>'
        )

    def message(a, b, y, label, color=BLUE, dashed=False):
        direction = 1 if b > a else -1
        source_active = any(x == a and start <= y <= end for x, start, end, _ in activations)
        target_active = any(x == b and start <= y <= end for x, start, end, _ in activations)
        start_x = a + 5 * direction if source_active else a
        end_x = b - 5 * direction if target_active else b
        d.arrow([(start_x, y), (end_x, y)], color, dashed)
        d.text((a + b) / 2, y - 14, label, 21, color, "middle")

    d.region(285, 320, 460, 125, "T1 · 同一个业务事务", GREEN)
    message(120, 380, 295, "1. 输入 + 请求键", CYAN)
    message(380, 640, 400, "2. Message + Run + 关联", GREEN)
    message(380, 120, 495, "3. 返回已接受", MUTED, True)
    message(900, 640, 590, "4. 扫描 / 授权 / 领取", AMBER)
    message(900, 1680, 685, "5. 当前：所有策略先查询 SDK 存档", RED)
    message(900, 1160, 785, "6. 选择策略并启动", BLUE)
    message(1160, 1680, 880, "7. 普通聊天：执行图与 checkpoint", BLUE)
    message(1160, 640, 980, "8. hooks 保存实际动作、用量和进度", GREEN)
    message(1160, 900, 1080, "9. 返回候选结果", BLUE, True)
    message(900, 1420, 1180, "10. store.persist → 注入的 PublishRun", PURPLE)
    d.region(540, 1225, 990, 135, "T2 · 授权复核 + 稳定结果 + 正式消息 + 终态 + 释放位置", GREEN)
    message(1420, 640, 1310, "11. 同一 Session 原子保存；失败整体回滚", GREEN)
    message(120, 640, 1430, "12. history / SSE 读取已提交快照", CYAN)
    message(640, 120, 1515, "13. 展示持久化状态与结果", MUTED, True)

    d.box(
        40,
        710,
        630,
        140,
        "并行看护与停止",
        [
            "协调器 watcher 检查取消、撤权、超时并定期保存。",
            "取消请求先写业务库；断开 SSE 不会自动取消 Run。",
        ],
        AMBER,
    )
    d.box(
        55,
        1560,
        1690,
        95,
        "边界与风险",
        [
            "模型 / MCP 等待不占业务事务；第 5 步越过了策略边界，使不使用此 SDK 的 CI 也受存档损坏影响。"
        ],
        RED,
    )
    d.save("runtime-scheduling")


def proposed():
    d = Diagram(
        1600,
        1800,
        "建议的职责关系｜共同执行机制，专业规则提供确定输入",
        "这是待实施示例。保留模块化单体、共享数据库和两个业务事务，不增加微服务或消息总线。",
        "PROPOSED · OWNERSHIP",
    )
    d.box(
        70,
        170,
        1460,
        95,
        "api · HTTP 入口与只读观察",
        ["身份解析 / 请求 DTO / 响应 / SSE；将业务命令交给应用用例。"],
        CYAN,
    )
    d.box(
        70,
        355,
        1460,
        150,
        "use_cases · 跨模块流程与运行政策",
        [
            "提交 / 准备 RunSpec / 授权组合 / 专业策略选择 / 原子发布",
            "在接受与发布时组织共用事务；bootstrap 只负责装配这些实现。",
        ],
        PURPLE,
    )
    d.box(
        70,
        650,
        420,
        150,
        "conversations",
        ["消息 / 顺序 / 上下文 / 结果引用", "不直接读取 snapshot.ci 决定规则。"],
        CYAN,
    )
    d.box(
        590,
        650,
        420,
        150,
        "配置资产视图",
        ["agents / skills / 模型连接 / 规则", "提供各自的配置与当前许可。"],
        GREEN,
    )
    d.box(
        1110,
        650,
        420,
        150,
        "CI 专业规则",
        ["目标范围 / 方法 / 证据校验", "提供专业策略与限制，不自建通用循环。"],
        RED,
    )
    d.box(70, 935, 420, 110, "auth · 身份与基础权限", ["运行许可再与资产及专业范围组合。"], CYAN)
    d.box(
        590,
        935,
        420,
        170,
        "execution · 共同生命周期",
        [
            "准入 / 状态转换 / 取消 / 动作",
            "统一记账 / 预算机制 / 稳定结果",
            "恢复按执行策略需要启用。",
        ],
        AMBER,
    )
    d.box(590, 1195, 420, 100, "小而明确的执行契约", ["模型 / 动作 / 恢复 / 发布接口"], AMBER)
    d.box(
        70,
        1370,
        420,
        150,
        "框架适配",
        ["SDK 事件 → 自有内容更新", "图状态与 checkpoint 留在适配内部。"],
        BLUE,
    )
    d.box(
        1110,
        1370,
        420,
        150,
        "工具适配",
        ["GitHub / MCP / 访问范围", "专业限制组合到共同动作机制。"],
        BLUE,
    )
    d.box(70, 1600, 420, 90, "llm · 模型与网络适配", color=BLUE)
    d.box(590, 1450, 420, 110, "业务数据库", ["各模块拥有数据，共用事务机制。"], GREEN)
    d.box(1110, 1600, 420, 90, "GitHub 等外部系统", color=BLUE)
    d.arrow([(800, 265), (800, 355)], CYAN)
    d.arrow([(70, 465), (35, 465), (35, 990), (70, 990)], CYAN)
    for x in (280, 800, 1320):
        d.arrow([(x, 505), (x, 650)], PURPLE)
    d.arrow([(490, 465), (535, 465), (535, 1010), (590, 1010)], PURPLE)
    d.arrow([(1010, 1010), (1060, 1010), (1060, 465), (1110, 465)], AMBER, True)
    d.text(470, 891, "接受 / 调度", 19, PURPLE)
    d.text(1080, 891, "完成意图", 19, AMBER)
    d.arrow([(800, 1105), (800, 1195)], AMBER)
    d.arrow([(590, 1245), (280, 1245), (280, 1370)], BLUE, True)
    d.arrow([(1010, 1245), (1320, 1245), (1320, 1370)], BLUE, True)
    d.arrow([(800, 1295), (800, 1450)], GREEN)
    d.arrow([(280, 1520), (280, 1600)], BLUE)
    d.arrow([(1320, 1520), (1320, 1600)], BLUE)
    d.text(70, 1080, "实线：运行时调用与保存", 20, MUTED)
    d.text(70, 1115, "虚线：经契约注入或完成回调", 20, MUTED)
    d.text(
        70,
        1730,
        "正式交付统一读取 RunResult（正文与结构化报告）；progress 仅表达过程，Message 引用结果。",
        22,
        WHITE,
    )
    d.save("proposed-boundaries")


if __name__ == "__main__":
    dependencies()
    scheduling()
    proposed()
