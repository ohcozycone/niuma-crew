"""Generate the reviewed boundaries and complete request flow as standalone SVGs."""

from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLORS = {
    "cyan": "#22d3ee",
    "green": "#34d399",
    "purple": "#a78bfa",
    "amber": "#fbbf24",
    "gray": "#94a3b8",
}


class Diagram:
    def __init__(self, width, height, title, subtitle):
        self.width, self.height = width, height
        self.edges, self.boxes, self.labels = [], [], []
        self.title, self.subtitle = title, subtitle
        self.text(48, 70, title, 34, weight=700)
        self.text(48, 112, subtitle, 20, color="gray")
        self.text(width - 48, 150, "当前实施 · 职责边界 · 2026-10-27", 17, anchor="end")

    def text(self, x, y, value, size=21, color=None, anchor="start", weight=400):
        fill = COLORS.get(color, "#e7edf7")
        self.labels.append(
            f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(value)}</text>'
        )

    def box(self, x, y, w, h, title, lines=(), color="green"):
        self.boxes.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#0f172a"/>'
        )
        self.boxes.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" '
            f'fill="{COLORS[color]}" fill-opacity="0.085" stroke="{COLORS[color]}" stroke-width="1.7"/>'
        )
        self.text(x + 20, y + 36, title, 24, color, weight=600)
        for i, line in enumerate(lines):
            self.text(x + 20, y + 73 + i * 31, line, 20)

    def arrow(self, x1, y1, x2, y2, dashed=False, label=None):
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        self.edges.append(
            f'<path d="M{x1} {y1}L{x2} {y2}" fill="none" stroke="#94a3b8" '
            f'stroke-width="1.8" marker-end="url(#arrow)"{dash}/>'
        )
        if label:
            self.text((x1 + x2) / 2, (y1 + y2) / 2 - 10, label, 17, anchor="middle")

    def path(self, points, dashed=False):
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        self.edges.append(
            f'<path d="{points}" fill="none" stroke="#94a3b8" stroke-width="1.8" '
            f'marker-end="url(#arrow)"{dash}/>'
        )

    def frame(self, x, y, w, h, title):
        self.boxes.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="none" '
            f'stroke="#a78bfa" stroke-width="1.4" stroke-dasharray="8 5"/>'
        )
        self.text(x + 18, y + 28, title, 19, "purple")

    def save(self, name):
        top = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'role="img" aria-labelledby="title desc"><title id="title">{escape(self.title)}</title>'
            f'<desc id="desc">{escape(self.subtitle)}</desc>',
            '<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" '
            'orient="auto"><path d="M0 0L10 4L0 8Z" fill="#94a3b8"/></marker>'
            '<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">'
            '<path d="M40 0H0V40" fill="none" stroke="#1e293b" stroke-width="0.5"/>'
            '</pattern><style>text{font-family:"JetBrains Mono","Noto Sans SC","PingFang SC",sans-serif}</style></defs>',
            f'<rect width="{self.width}" height="{self.height}" fill="#0f172a"/>',
            f'<rect width="{self.width}" height="{self.height}" fill="url(#grid)"/>',
        ]
        (HERE / name).write_text(
            "\n".join(top + self.edges + self.boxes + self.labels + ["</svg>"])
        )


def boundaries():
    d = Diagram(
        1680,
        1450,
        "先分职责，再看记录",
        "模块是做事的边界；Conversation、Message、Run 等记录写在所属模块内部。所有模块仍在同一应用。",
    )
    d.box(
        50,
        190,
        1580,
        100,
        "对话页面 · useConversation / useMessage",
        ["发送输入、显示回复、停止这次处理、浏览历史；一个对话作用域统一读取和观察。"],
        "cyan",
    )
    d.box(
        50,
        345,
        1580,
        100,
        "HTTP 对话分组 · router / service / streaming",
        ["按用户操作提供能力；response_id 就是助手消息 ID，不新增回复实体。"],
        "cyan",
    )
    d.box(
        50,
        500,
        1580,
        145,
        "请求编排与共享对话流程 · 不设全局协调目录",
        [
            "API 请求服务组织接受、停止、重试和反馈；简单配置直接调用所属服务。",
            "conversations 内 preparation / authorization / publication 供请求与后台共同使用。",
        ],
    )
    d.box(
        50,
        730,
        480,
        175,
        "对话模块 · conversations",
        [
            "Conversation：对话与顺序",
            "Message：用户内容与助手回复",
            "ConversationRun：关联与活动占用",
        ],
        "purple",
    )
    d.box(
        600,
        730,
        480,
        175,
        "执行模块 · execution",
        [
            "Run：一次处理尝试",
            "RunAction：实际动作与过程",
            "排队、时限、预算、停止与恢复",
        ],
        "green",
    )
    d.box(
        1150,
        730,
        480,
        175,
        "专业诊断 · ci_diagnosis",
        [
            "CiDiagnosis：来源、报告、反馈",
            "专业执行器核对证据与覆盖",
            "共用执行控制，保留专业规则",
        ],
        "amber",
    )
    d.box(
        50,
        1000,
        480,
        165,
        "身份与员工配置",
        ["auth / agents / skills", "模型连接 / 公司规则", "本模块服务提供规则与配置"],
        "gray",
    )
    d.box(
        600,
        1000,
        480,
        165,
        "普通 Agent · agent_runtime",
        [
            "实际模型与工具循环",
            "SDK 片段、完成判断和恢复格式",
            "只得到受限控制，不得到 Store",
        ],
        "green",
    )
    d.box(
        1150,
        1000,
        480,
        165,
        "SDK 专用存档",
        [
            "由装配入口单独注入适配器",
            "用于继续运行或补交候选答复",
            "已保存历史不依赖它",
        ],
        "purple",
    )
    d.box(
        600,
        1260,
        480,
        100,
        "模型服务 / 方法资源 / MCP",
        ["外部等待发生在业务事务之外。"],
        "gray",
    )
    d.arrow(840, 290, 840, 345)
    d.arrow(840, 445, 840, 500)
    d.arrow(290, 645, 290, 730)
    d.arrow(840, 645, 840, 730)
    d.arrow(1390, 645, 1390, 730)
    d.arrow(790, 905, 790, 1000, label="执行")
    d.arrow(990, 1000, 990, 905, dashed=True, label="受限控制")
    d.arrow(1150, 820, 1080, 820, dashed=True)
    d.text(1115, 802, "控制", 16, anchor="middle")
    d.arrow(1080, 1080, 1150, 1080, dashed=True)
    d.text(1115, 1062, "存档", 16, anchor="middle")
    d.arrow(840, 1165, 840, 1260)
    d.path("M50 1080H25V575H50", dashed=True)
    d.path("M1630 850H1650V1310H1080")
    d.text(
        48,
        1410,
        "实线：调用与业务协作　虚线：受限控制、配置或存档　|　图中没有 Thread、Turn 或通用 Item 层",
        18,
        "gray",
    )
    d.save("target-boundaries.svg")


def sequence():
    d = Diagram(
        1800,
        1580,
        "一次发送：内容、运行和交付怎样配合",
        "先接受再执行；外部调用不占业务事务；只有最终提交成功后，页面才看到成功终态。",
    )
    actors = [
        (160, "浏览器", "输入与观察", "cyan"),
        (510, "请求与共享流程", "API 请求 / 对话发布", "cyan"),
        (860, "业务存储", "对话内容 / CI 数据", "purple"),
        (1210, "执行宿主", "Run / 动作 / 调度", "green"),
        (1560, "具体执行器", "普通 Agent 或 CI", "amber"),
    ]
    for x, title, sub, color in actors:
        d.box(x - 135, 190, 270, 100, title, [sub], color)
        d.edges.append(
            f'<path d="M{x} 290V1450" stroke="#334155" stroke-dasharray="6 5" fill="none"/>'
        )
    d.arrow(160, 340, 510, 340, label="1. 发送内容与固定请求键")
    d.frame(440, 375, 840, 235, "接受事务：以下记录一起提交")
    d.arrow(510, 435, 860, 435, label="2. 输入 + 空助手回复")
    d.arrow(510, 495, 1210, 495, label="3. Run + 关联 + 活动占用")
    d.text(675, 580, "4. 提交；失败全部回滚", 20, "purple")
    d.arrow(510, 650, 160, 650, dashed=True, label="5. 202 + 稳定回复 ID")
    d.arrow(1210, 720, 1560, 720, label="6. 排队后启动执行")
    d.arrow(1560, 785, 1210, 785, dashed=True, label="7. 检查、预算与动作记录")
    d.path("M1560 835H1690V890H1560")
    d.text(1540, 925, "8. 模型 / 工具循环", 19, "amber", "middle")
    d.arrow(1560, 980, 1210, 980, dashed=True, label="9. 普通进度与候选输出")
    d.arrow(1210, 1040, 510, 1040, label="10. 请求业务发布")
    d.frame(440, 1080, 840, 250, "发布事务：状态与内容一起决定")
    d.arrow(510, 1145, 860, 1145, label="11. 回复正文 + CI 报告")
    d.arrow(510, 1210, 1210, 1210, label="12. Run 终态 + 释放占用")
    d.text(675, 1295, "13. 提交；失败不宣告成功", 20, "purple")
    d.arrow(510, 1400, 160, 1400, dashed=True, label="14. GET / SSE 返回已保存快照")
    d.text(
        48,
        1515,
        "停止与发布按同一写入顺序决定；观察断线不取消后台；重试新建处理和回复，保留原问题。",
        20,
        "gray",
    )
    d.text(
        48,
        1548,
        "发布回调指向 conversations/publication；后台不调用 API 请求服务。",
        18,
        "gray",
    )
    d.save("request-lifecycle.svg")


if __name__ == "__main__":
    boundaries()
    sequence()
    print("Generated target-boundaries.svg and request-lifecycle.svg")
