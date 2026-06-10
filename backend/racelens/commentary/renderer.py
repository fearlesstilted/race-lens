"""Deterministic commentary: insight → human text (PLAN.md §13).

No AI, no NLP — every insight type has a template per (lang, level), filled
from the insight's evidence. An optional LLM polish layer can come later;
it would sit on top of this, never replace it.
"""
from __future__ import annotations

from typing import Any

# key: (base_type, lang, level)
TEMPLATES: dict[tuple[str, str, str], str] = {
    ("TRAFFIC_RISK", "en", "pro"):
        "{a} is losing ~{pace_s:.1f}s/lap behind {b}, gap {gap:.1f}s. "
        "Track position pressure builds — an early stop becomes viable.",
    ("TRAFFIC_RISK", "en", "beginner"):
        "{a} is faster but stuck behind {b}. Overtaking here is hard, so "
        "the team may pit {a} to get clear air.",
    ("TRAFFIC_RISK", "ru", "pro"):
        "{a} теряет ~{pace_s:.1f}с/круг за {b}, отставание {gap:.1f}с. "
        "Ранний пит-стоп становится оправданным.",
    ("TRAFFIC_RISK", "ru", "beginner"):
        "{a} едет быстрее, но заперт за {b}. Обгонять тут почти негде, "
        "поэтому команда может позвать {a} в боксы ради чистого воздуха.",

    ("DRS_TRAIN", "en", "pro"):
        "DRS train of {cars} cars behind {head}; intervals inside DRS range, "
        "overtaking probability low until the train breaks.",
    ("DRS_TRAIN", "en", "beginner"):
        "{cars} cars are queued up behind {head}. Everyone has DRS, so "
        "nobody gains an advantage — expect a stalemate.",
    ("DRS_TRAIN", "ru", "pro"):
        "DRS-паровоз из {cars} машин за {head}; интервалы в зоне DRS, "
        "вероятность обгонов низкая, пока цепь не разорвётся.",
    ("DRS_TRAIN", "ru", "beginner"):
        "За {head} выстроилась очередь из {cars} машин. DRS есть у всех, "
        "поэтому преимущества ни у кого нет — позиции заморожены.",

    ("PIT_WINDOW", "en", "pro"):
        "{a} has a free stop: {margin:.1f}s of margin over the pit loss to "
        "the next car behind, tyres {age} laps old.",
    ("PIT_WINDOW", "en", "beginner"):
        "{a} can pit without losing a position — the gap behind is big "
        "enough to cover the stop.",
    ("PIT_WINDOW", "ru", "pro"):
        "У {a} «бесплатный» пит-стоп: запас {margin:.1f}с сверх потери на "
        "пит-лейне, резине {age} кругов.",
    ("PIT_WINDOW", "ru", "beginner"):
        "{a} может заехать в боксы и не потерять позицию — разрыв до машины "
        "сзади перекрывает потерю времени.",

    ("UNDERCUT_RISK", "en", "pro"):
        "Undercut threat on {b}: {a} is {gap:.1f}s back on {age}-lap tyres "
        "with matching pace. Defending stop window is open.",
    ("UNDERCUT_RISK", "en", "beginner"):
        "{a} is close enough to try an undercut: pit first, get fresh "
        "tyres, and jump {b} during the stops.",
    ("UNDERCUT_RISK", "ru", "pro"):
        "Угроза ундерката для {b}: {a} в {gap:.1f}с на резине возрастом "
        "{age} кругов при равном темпе. Окно защитного пит-стопа открыто.",
    ("UNDERCUT_RISK", "ru", "beginner"):
        "{a} достаточно близко для ундерката: заехать в боксы первым, взять "
        "свежую резину и опередить {b} за счёт пит-стопов.",
}

_BASE_TYPES = ("TRAFFIC_RISK", "DRS_TRAIN", "PIT_WINDOW", "UNDERCUT_RISK")


def _params(base: str, ins: dict[str, Any]) -> dict[str, Any]:
    ev = ins["evidence"]
    ids = ins["driver_ids"]
    if base == "TRAFFIC_RISK":
        return {"a": ids[0], "b": ids[1],
                "pace_s": ev["pace_delta_ms"] / 1000, "gap": ev["interval_s"]}
    if base == "DRS_TRAIN":
        return {"cars": ev["cars"], "head": ev["head"]}
    if base == "PIT_WINDOW":
        return {"a": ids[0], "margin": ev["margin_s"], "age": ev["tyre_age_laps"]}
    if base == "UNDERCUT_RISK":
        return {"a": ids[0], "b": ids[1],
                "gap": ev["interval_s"], "age": ev["attacker_tyre_age_laps"]}
    return {}


def render(insight: dict[str, Any], lang: str = "en", level: str = "pro") -> str:
    base = next((b for b in _BASE_TYPES if insight["type"].startswith(b)), None)
    if base is None:
        return insight["type"]  # unknown types degrade gracefully
    template = TEMPLATES.get((base, lang, level)) or TEMPLATES[(base, "en", "pro")]
    return template.format(**_params(base, insight))


def render_all(insights: list[dict[str, Any]], lang: str = "en", level: str = "pro") -> list[dict]:
    return [
        {
            "insight_id": i["insight_id"],
            "severity": i["severity"],
            "lap": i["lap"],
            "text": render(i, lang, level),
        }
        for i in insights
    ]
