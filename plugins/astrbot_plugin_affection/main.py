"""好感度：把心情、亲密度、相处天数、承诺和聊天量合成分数，随时可查。

数据来源：
- data/mood/<umo>.json      心情/亲密度/欲望（astrbot_plugin_mood 维护）
- data/chat_bridge/messages.jsonl  聊天条数
- data/memory/promises.md   答应过的事
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter

ROOT = Path(r"C:\Users\17509\Desktop\deep seekworkplace\qqbot")
MOOD_DIR = ROOT / "astrbot" / "data" / "mood"
MOOD_FILE = MOOD_DIR / "qqbot_FriendMessage_1750987885.json"
BRIDGE = ROOT / "astrbot" / "data" / "chat_bridge" / "messages.jsonl"
PROMISES = ROOT / "astrbot" / "data" / "memory" / "promises.md"
FIRST_DAY = dt.date(2026, 10, 24)      # 认识的日子

LEVELS = [
    (20, "还很生疏"),
    (40, "有点熟了"),
    (60, "相处得还行"),
    (75, "挺亲近的"),
    (90, "黏上你了"),
    (101, "离不开了"),
]


def _mood() -> dict:
    try:
        return json.loads(MOOD_FILE.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {"mood": 60, "intimacy": 60, "desire": 20}


def _messages() -> int:
    try:
        return sum(1 for line in BRIDGE.read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:  # noqa: BLE001
        return 0


def _promises() -> int:
    try:
        return sum(1 for ln in PROMISES.read_text(encoding="utf-8").splitlines() if ln.startswith("- "))
    except Exception:  # noqa: BLE001
        return 0


def _score() -> tuple[int, dict]:
    st = _mood()
    mood = int(st.get("mood", 60))
    intimacy = int(st.get("intimacy", 60))
    desire = int(st.get("desire", 20))
    days = max((dt.date.today() - FIRST_DAY).days, 0)
    msgs = _messages()
    promises = _promises()

    base = intimacy * 0.40 + mood * 0.25 + min(desire, 100) * 0.10
    bonus = min(days * 1.2, 15) + min(msgs / 40.0, 6) + min(promises * 2.0, 8)
    score = int(max(0, min(100, round(base + bonus))))
    detail = {
        "心情": mood,
        "亲密度": intimacy,
        "想黏人": desire,
        "认识天数": days,
        "流水条数": msgs,
        "承诺数": promises,
        "加成": round(bonus, 1),
    }
    return score, detail


def _level(score: int) -> str:
    for limit, name in LEVELS:
        if score < limit:
            return name
    return "离不开了"


def _bar(score: int) -> str:
    filled = max(0, min(10, round(score / 10)))
    return "█" * filled + "░" * (10 - filled)


def _card() -> str:
    score, d = _score()
    desire = d["想黏人"]
    desire_word = (
        "很想黏你" if desire >= 70 else "有点想亲近" if desire >= 45 else "没那个心思"
    )
    lines = [
        f"好感度 {score}/100 {_bar(score)} {_level(score)}",
        f"心情 {d['心情']}/100　亲密 {d['亲密度']}/100",
        f"想黏 {desire}/100（{desire_word}）",
        f"相处 {d['认识天数']} 天　流水 {d['流水条数']} 条　承诺 {d['承诺数']} 件",
    ]
    return "\n".join(lines)


class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        self.context = context

    @filter.command("好感度")
    async def cmd_affection(self, event: AstrMessageEvent):
        """看她现在对你的好感度。"""
        yield event.plain_result(_card())

    @filter.llm_tool(name="check_affection")
    async def tool_affection(self, event: AstrMessageEvent) -> str:
        """当你被问到「你有多喜欢我」「好感度多少」时，查一下自己的真实好感度再回答。

        返回的是分数和分项，不要照念，用你自己的口气说。
        """
        return _card()
