"""Build the current backend view; keep the older proposal view opt-in.

Each view declares one relationship vocabulary. Target cells are responsibility
locations, never claims that the corresponding code already exists.
"""

import argparse
from html import escape
from pathlib import Path

from diagram_paths import destination

HERE = Path(__file__).parent
C = {
    "cyan": "#69c7dc",
    "green": "#78c8b0",
    "purple": "#c0a6e7",
    "amber": "#e7bd77",
    "blue": "#8bacdf",
    "gray": "#a2b1c8",
    "rose": "#e59ca7",
}


class SVG:
    def __init__(self, title, subtitle, height, badge):
        self.height = height
        self.base = [
            f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 {height}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title><desc id="desc">{escape(subtitle)}</desc>
<defs><marker id="arrow" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><path d="M0 0L9 3.5L0 7Z" fill="#a2b1c8"/></marker>
<style>text{{font-family:'PingFang SC','Noto Sans SC',sans-serif;fill:#e4ebf5;font-size:20px}}.title{{font-size:37px;font-weight:650}}.sub{{font-size:19px;fill:#a2b1c8}}.label{{font-size:23px;font-weight:600}}.name{{font-size:21px;font-weight:600}}.small{{font-size:17px;fill:#b3c1d5}}.note{{font-size:19px;fill:#d0dbea}}.code{{font-size:16px;fill:#a2b1c8;font-family:'SF Mono','PingFang SC',monospace}}.edge{{fill:none;stroke:#a2b1c8;stroke-width:2;marker-end:url(#arrow)}}</style></defs>
<rect width="1600" height="{height}" fill="#0d1728"/>
<rect x="48" y="42" width="48" height="5" rx="2" fill="#78c8b0"/>
'''
        ]
        self.edges, self.nodes = [], []
        self.text(48, 101, title, "title")
        self.text(48, 144, subtitle, "sub")
        self.text(1552, 56, badge, "code", "end")

    def text(self, x, y, s, cls="note", anchor="start", color=None):
        extra = f' style="fill:{C.get(color, color)}"' if color else ""
        self.nodes.append(
            f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}"{extra}>{escape(s)}</text>'
        )

    def region(self, x, y, w, h, color="gray", dash=False, fill="#121f33"):
        dashed = ' stroke-dasharray="8 5"' if dash else ""
        self.base.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{C[color]}" stroke-opacity=".45"{dashed}/>'
        )

    def card(self, x, y, w, h, title, lines=(), color="green", dash=False):
        dashed = ' stroke-dasharray="7 5"' if dash else ""
        self.nodes.append(
            f'<g data-component="card"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#18283e" stroke="{C[color]}"{dashed}/>'
        )
        self.text(x + 18, y + 34, title, "name", color=color)
        for i, line in enumerate(lines):
            self.text(x + 18, y + 65 + i * 26, line, "small")
        self.nodes.append("</g>")

    def edge(self, d, label=None, x=0, y=0):
        self.edges.append(f'<path d="{d}" class="edge"/>')
        if label:
            self.text(x, y, label, "small")

    def footer(self, lines, date="2026-10-23"):
        y = self.height - 114
        self.base.append(f'<path d="M48 {y - 22}H1552" stroke="#30435e"/>')
        for i, line in enumerate(lines):
            self.text(48, y + i * 29, line, "small")
        self.text(
            1552, self.height - 25, f"NIUMACREW / BACKEND / {date}", "code", "end"
        )

    def save(self, name):
        destination(name).write_text(
            "\n".join(self.base + self.edges + self.nodes + ["</svg>"]), encoding="utf8"
        )


def current():
    d = SVG(
        "后端现状｜业务操作、可靠执行与 Agent 循环",
        "同一后端进程、同一业务数据库；箭头表示主要调用，省略查询、返回与部分共用事务连线。",
        1300,
        "CURRENT · 2026-10-30",
    )
    d.card(
        48,
        200,
        1504,
        90,
        "应用装配 · bootstrap",
        [
            "lifespan 装配业务服务、ConversationService、发布与授权回调、checkpoint 和单个 Runner。"
        ],
        "gray",
    )
    d.card(
        48,
        335,
        1504,
        92,
        "HTTP 入口 · api/routes",
        ["配置管理 · 对话与消息 · 提交 / 取消 / 重试 · 历史、实际动作与只读 SSE"],
        "cyan",
    )
    d.card(
        48,
        505,
        460,
        151,
        "员工配置与执行依据",
        [
            "agents / skills / model_connections",
            "规则、装配和修订由所属模块维护",
            "受信配置读取复用调用方 Session",
        ],
        "green",
    )
    d.card(
        570,
        505,
        460,
        151,
        "对话操作 · conversations",
        [
            "ConversationService / PublishRun",
            "接受：消息 + Run + 关联同事务",
            "发布：正文、文件关联及终态同事务",
        ],
        "purple",
    )
    d.card(
        1092,
        505,
        460,
        151,
        "身份与访问控制 · auth",
        [
            "service：身份及登录会话有效性",
            "permissions：操作与资源范围",
            "业务入口、动作和发布前执行检查",
        ],
        "green",
    )
    d.card(
        48,
        775,
        460,
        151,
        "内容与查询 · conversations",
        [
            "Conversation / Message / ConversationRun",
            "保存原文、最终正文和运行关联",
            "历史、快照与 SSE 读取已提交内容",
        ],
        "cyan",
    )
    d.card(
        570,
        775,
        460,
        151,
        "可靠执行 · execution",
        [
            "Run / RunAction / RunControl",
            "排队、容量、预算、取消与恢复",
            "coordinator 调用准备与发布回调",
        ],
        "amber",
    )
    d.card(
        1092,
        775,
        460,
        151,
        "Agent 循环 · agent_runtime",
        [
            "组织模型、技能加载和已许可工具",
            "SDK 消息与产品 Message 分开",
            "通过 RuntimeControl 记动作和用量",
        ],
        "amber",
    )
    d.card(
        48,
        1030,
        460,
        105,
        "业务数据库 · infrastructure",
        ["配置 / Message / Run / RunAction", "共用业务库，通过短事务提交"],
        "blue",
    )
    d.card(
        570,
        1030,
        460,
        105,
        "模型协议 · llm",
        ["连接模型、接收响应和用量", "显式配置与受控网络"],
        "blue",
    )
    d.card(
        1092,
        1030,
        460,
        105,
        "工具、文件与 SDK 恢复",
        ["tools / files / sandboxes 提供资源", "agent_runtime 管理每轮 checkpoint"],
        "gray",
    )
    for x in (278, 800, 1322):
        d.edge(f"M{x} 427V505")
    d.text(827, 477, "调用", "small")
    d.edge("M800 656V706H278V775", "业务消息与关联", 330, 696)
    d.edge("M870 656V775", "执行准入", 886, 738)
    d.edge("M730 775V656", "结果发布", 636, 747)
    d.edge("M1030 850H1092", "执行", 1044, 832)
    d.edge("M1092 903H1030", "记账", 1044, 886)
    d.edge("M1190 926V978H800V1030", "调用模型", 862, 968)
    d.edge("M1410 926V1030", "按许可使用", 1427, 992)
    d.edge("M148 926V1030", "短事务", 167, 1003)
    d.footer(
        [
            "稳定产品内容由业务库保存；SDK checkpoint 只用于内部执行与恢复，损坏不阻止已发布历史读取。",
            "execution 使用注入的准备、复核和发布回调；Agent 循环不取得业务 Session 或 RunStore。",
        ],
        date="2026-10-30",
    )
    d.save("backend-current")


def modules():
    d = SVG(
        "后端重设计｜交流、工作与执行各有归属",
        "阶段 A 已实现；任务、知识与通用工具后续建设。箭头表示调用或使用，省略查询与返回。",
        1710,
        "DRAFT · 2026-10-26",
    )
    d.card(
        80,
        220,
        650,
        150,
        "对话 · conversations",
        [
            "对话归属、产品消息与上下文选择",
            "发布助手消息；不拥有执行器或任务验收",
            "首个改造入口：现有聊天",
        ],
        "cyan",
    )
    d.card(
        870,
        220,
        650,
        150,
        "任务 · tasks",
        [
            "工作目标、固定输入、成果与验收",
            "可以没有对话；一次任务可以有多次尝试",
            "后续按真实工作需求建设",
        ],
        "cyan",
        dash=True,
    )
    d.card(
        80,
        500,
        1440,
        140,
        "应用用例 · use_cases",
        [
            "组织跨模块短事务：接受输入 + 创建 Run；发布结果 + 更新业务主体 + Run 终态",
            "业务规则由各模块提供；结果发布适配器由 bootstrap 组合，共用事务、不自行提交",
        ],
        "purple",
    )
    d.card(
        80,
        770,
        1440,
        180,
        "执行系统 · execution（合并 runs / runtime 的所有权）",
        [
            "Run / RunSpec / RunAction / RunResult：身份、依据、实际动作、稳定结果",
            "准入、预算、调度、取消、恢复与终态；模型和工具调用在业务事务外",
            "内部隔离 SDK 与 checkpoint；不持有对话、任务验收或 CI 专属字段",
        ],
        "amber",
    )
    assets = [
        (80, "员工 · agents", ["岗位与装配引用", "提供本次配置视图"], "配置"),
        (380, "方法 · skills", ["标准内容与资源", "方法不等于许可"], "方法"),
        (680, "工具 · tools", ["连接、目录与许可", "受控实际调用"], "工具"),
        (980, "知识 · knowledge", ["资料版本与发布", "检索和来源定位"], "检索"),
        (
            1280,
            "模型连接与调用",
            ["model_connections / llm", "秘密管理 / 协议适配"],
            "模型",
        ),
    ]
    for x, title, lines, label in assets:
        d.card(x, 1110, 240, 140, title, lines, "green")
        d.edge(f"M{x + 120} 950V1110")
        d.text(x + 140, 1040, label, "small")
    d.card(
        80,
        1380,
        1440,
        105,
        "共同支撑 · auth / infrastructure",
        ["身份、当前操作范围、业务数据库与事务机制；不是所有模块依次经过的一条流水线"],
        "gray",
    )
    d.edge("M405 500V370")
    d.text(425, 440, "校验 / 发布消息", "small")
    d.edge("M1195 500V370")
    d.text(1215, 440, "校验 / 发布成果", "small")
    d.edge("M500 640V770")
    d.text(520, 710, "准入 / 取消 / 重试", "small")
    d.edge("M1120 770V640")
    d.text(1140, 710, "调用注入的结果发布接口", "small")
    d.footer(
        [
            "稳定内容：Message / Deliverable 引用 RunResult；SDK checkpoint 只承担内部执行与恢复，不是产品历史库。",
            "后续组合：Plan 表达计划，规划模式约束本次工作；Goal 在一次 Run 收尾后决定是否续跑。",
            "实线：运行时调用或使用，非源码导入；虚线框：后续任务模块。目标图不表示上述能力均已实现。",
        ],
        date="2026-10-26",
    )
    d.save("backend-modules")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", choices=("current", "proposal"), default="current")
    args = parser.parse_args()
    if args.view == "current":
        current()
    else:
        modules()
