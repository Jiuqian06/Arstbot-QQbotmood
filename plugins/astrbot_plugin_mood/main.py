"""情绪状态：让她的心情跨轮次存在，而不是每句重新做人。

state 存在 data/mood/<umo>.json，每次请求注入，靠简单规则更新：
- 被夸 mood↑ / 被敷衍 mood↓ / 被骂 mood↓↓
- 亲近的话 desire↑ / 长时间不见 desire 和想念都↑
- 没人理她，mood 慢慢往下掉
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter

ROOT = Path(r"C:\Users\17509\Desktop\deep seekworkplace\qqbot")
STATE_DIR = ROOT / "astrbot" / "data" / "mood"
OWNER_ID = "1750987885"
GROUP_MOOD = True                 # 群里也有情绪
GROUP_WHITELIST: list[str] = []   # 空 = 所有群

PRAISE = ("厉害", "真棒", "可爱", "好看", "喜欢你", "爱你", "乖", "厉害咯", "你最")
COLD = ("嗯", "哦", "随便", "都行", "行吧", "知道了", "哦哦", "嗯嗯")
INTIMATE = ("抱", "摸头", "亲", "想你了", "贴", "蹭", "抱抱", "要你", "黏")
HURT = ("滚", "闭嘴", "烦死", "没用", "蠢", "笨鱼", "工具")


def _path(umo: str) -> Path:
    safe = re.sub(r"[^0-9A-Za-z_.-]", "_", umo)
    return STATE_DIR / f"{safe}.json"


def _load(umo: str) -> dict:
    p = _path(umo)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {
        "mood": 65,
        "intimacy": 70,
        "desire": 30,
        "ignored": 0,
        "cause": "",
        "updated": dt.datetime.now().isoformat(timespec="seconds"),
    }


def _save(umo: str, st: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    st["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    _path(umo).write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def _clamp(v: int) -> int:
    return max(0, min(100, v))


def _allowed(umo: str) -> bool:
    if OWNER_ID in umo and "friendmessage" in umo.lower():
        return True
    if GROUP_MOOD and "groupmessage" in umo.lower():
        return not GROUP_WHITELIST or any(g in umo for g in GROUP_WHITELIST)
    return False


def _decay(st: dict) -> dict:
    """隔得越久，心情和亲密度越会往下掉；想黏人的劲儿反而会涨。"""
    try:
        last = dt.datetime.fromisoformat(st.get("updated", ""))
    except Exception:  # noqa: BLE001
        return st
    hours = (dt.datetime.now() - last).total_seconds() / 3600
    if hours < 0.5:
        return st
    st["mood"] = _clamp(int(st.get("mood", 60) - min(hours * 2.0, 30)))
    st["intimacy"] = _clamp(int(max(40, st.get("intimacy", 60) - hours * 0.8)))
    st["desire"] = _clamp(int(st.get("desire", 20) + min(hours * 1.5, 20)))
    if not st.get("cause"):
        st["cause"] = "有阵子没说话了，有点想"
    return st


def _update(st: dict, text: str, allow_desire: bool = True) -> dict:
    t = (text or "").strip()
    low = t.replace(" ", "")

    if any(k in t for k in PRAISE):
        st["mood"] = _clamp(st["mood"] + 6)
        st["intimacy"] = _clamp(st["intimacy"] + 4)
        st["cause"] = "刚被夸了，心里舒坦"
    elif any(k in t for k in HURT):
        st["mood"] = _clamp(st["mood"] - 10)
        st["intimacy"] = _clamp(st["intimacy"] - 4)
        st["ignored"] += 1
        st["cause"] = "刚被凶了，心里堵着"
    elif len(low) <= 3 and any(k in low for k in COLD):
        st["mood"] = _clamp(st["mood"] - 7)
        st["ignored"] += 1
        st["cause"] = "被一句敷衍打发了，有点烦"
    elif any(k in t for k in INTIMATE):
        st["desire"] = _clamp(st["desire"] + 20)
        st["intimacy"] = _clamp(st["intimacy"] + 5)
        st["mood"] = _clamp(st["mood"] + 3)
        st["cause"] = "刚被这么一说，心有点软"
    else:
        st["mood"] = _clamp(st["mood"] + (1 if len(t) > 12 else 0))
        if len(low) > 3:
            st["ignored"] = 0

    # 时间衰减：隔得越久越想人
    try:
        last = dt.datetime.fromisoformat(st["updated"])
        hours = (dt.datetime.now() - last).total_seconds() / 3600
        if hours > 3:
            st["desire"] = _clamp(st["desire"] + int(min(hours, 12)))
            st["mood"] = _clamp(st["mood"] - 2)
            if not st["cause"]:
                st["cause"] = "有阵子没说话了，有点想"
    except Exception:  # noqa: BLE001
        pass

    if not any(k in t for k in INTIMATE):
        st["desire"] = _clamp(st["desire"] - 1)
    return st


def _describe(st: dict) -> str:
    mood, desire = st["mood"], st["desire"]
    mood_word = (
        "挺好" if mood >= 75 else "还行" if mood >= 55 else "有点低" if mood >= 35 else "很差"
    )
    desire_word = (
        "很想黏人" if desire >= 70 else "有点想要亲近" if desire >= 45 else "没那个心思"
    )
    parts = [f"心情 {mood}/100（{mood_word}）", f"亲密度 {st['intimacy']}/100"]
    parts.append(desire_word)
    if st.get("cause"):
        parts.append(st["cause"])
    if st.get("ignored", 0) >= 2:
        parts.append(f"最近被敷衍了 {st['ignored']} 次")
    return "；".join(parts)


class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        self.context = context

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def observe(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin or ""
        if not _allowed(umo):
            return
        st = _decay(_load(umo))
        st = _update(st, event.message_str or "", allow_desire=(OWNER_ID in umo))
        _save(umo, st)

    @filter.on_llm_request()
    async def inject(self, event: AstrMessageEvent, req) -> None:
        umo = event.unified_msg_origin or ""
        if not _allowed(umo):
            return
        st = _decay(_load(umo))
        req.system_prompt += (
            "\n\n【你现在的状态】"
            + _describe(st)
            + "。带着这个情绪说话，别压着；心情差就写在语气里，心情好就露出来。"
        )
