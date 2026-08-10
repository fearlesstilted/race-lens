"""Private, bounded Whisper profile evaluation; no audio or references leave disk."""
from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

MANIFEST_RECORDS = 50
MAX_MANIFEST_BYTES = 512 * 1024
MAX_AUDIO_BYTES = 10 * 1024 * 1024
F1_PROMPT = "Formula 1 team radio: box, pit, tyres, gap, delta, safety car, driver names."


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    model: str
    options: dict[str, Any]


CURRENT_PROFILE = Profile(
    "current-medium-int8", "medium", {"language": "en", "vad_filter": True},
)
PROMPTED_PROFILE = Profile(
    "prompted-medium-int8",
    "medium",
    {
        "language": "en",
        "vad_filter": True,
        "condition_on_previous_text": False,
        "initial_prompt": F1_PROMPT,
        "vad_parameters": {"min_silence_duration_ms": 350, "speech_pad_ms": 200},
    },
)
DISTIL_PROFILE = Profile(
    "distil-large-v3-int8", "distil-large-v3", {"language": "en", "vad_filter": True},
)
PROFILES = (CURRENT_PROFILE, PROMPTED_PROFILE, DISTIL_PROFILE)


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    wer: float
    keyword_accuracy: float
    latency_s: float


def _words(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.findall(r"[a-z0-9]+", normalized)


def _edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, expected in enumerate(reference, 1):
        current = [row]
        for column, actual in enumerate(hypothesis, 1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (expected != actual),
            ))
        previous = current
    return previous[-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    expected = _words(reference)
    if not expected:
        raise ValueError("reference transcript has no words")
    return _edit_distance(expected, _words(hypothesis)) / len(expected)


def load_manifest(path: Path) -> list[dict]:
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("evaluation manifest is missing or too large")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("evaluation manifest contains invalid JSON") from exc
        if not isinstance(value, dict) or not {"audio_path", "transcript"} <= set(value):
            raise ValueError("evaluation manifest record fields are invalid")
        if not set(value) <= {"audio_path", "transcript", "keywords"}:
            raise ValueError("evaluation manifest record fields are invalid")
        audio_value, transcript = value["audio_path"], value["transcript"]
        if (
            not isinstance(audio_value, str)
            or not audio_value
            or len(audio_value) > 2048
            or not isinstance(transcript, str)
            or not 0 < len(transcript) <= 5000
            or not _words(transcript)
        ):
            raise ValueError("evaluation manifest record is invalid")
        audio = Path(audio_value)
        if not audio.is_absolute():
            audio = path.parent / audio
        if (
            not audio.is_file()
            or audio.is_symlink()
            or not 0 < audio.stat().st_size <= MAX_AUDIO_BYTES
        ):
            raise ValueError("evaluation audio is missing or outside the size bound")
        keywords = value.get("keywords", [])
        if (
            not isinstance(keywords, list)
            or len(keywords) > 50
            or not all(isinstance(item, str) and 0 < len(item) <= 100 and _words(item) for item in keywords)
        ):
            raise ValueError("evaluation keywords are invalid")
        rows.append({"audio_path": audio, "transcript": transcript, "keywords": keywords})
    if len(rows) != MANIFEST_RECORDS:
        raise ValueError("evaluation manifest must contain exactly 50 records")
    return rows


def gate_profile(
    current: EvaluationMetrics, candidate: EvaluationMetrics,
) -> dict[str, float | bool | None]:
    relative_wer = (
        (current.wer - candidate.wer) / current.wer if current.wer > 0 else 0.0
    )
    keyword_points = candidate.keyword_accuracy - current.keyword_accuracy
    latency_ratio = candidate.latency_s / current.latency_s if current.latency_s > 0 else None
    return {
        "passed": (
            relative_wer + 1e-12 >= 0.20
            and keyword_points + 1e-12 >= 0.10
            and latency_ratio is not None
            and latency_ratio <= 1.25
        ),
        "relative_wer_improvement": relative_wer,
        "keyword_point_improvement": keyword_points,
        "latency_ratio": latency_ratio,
    }


def _default_model_factory(model: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model, device=device, compute_type=compute_type)


def _contains_keyword(hypothesis: list[str], keyword: str) -> bool:
    expected = _words(keyword)
    width = len(expected)
    return any(hypothesis[index:index + width] == expected for index in range(len(hypothesis) - width + 1))


def evaluate_manifest(
    path: Path,
    *,
    model_factory: Callable[[str, str, str], Any] = _default_model_factory,
    clock: Callable[[], float] = time.perf_counter,
) -> dict:
    records = load_manifest(path)
    profile_results: dict[str, dict] = {}
    metrics: dict[str, EvaluationMetrics] = {}
    for profile in PROFILES:
        model = model_factory(profile.model, "cpu", "int8")
        edits = words = keyword_hits = keyword_total = 0
        started = clock()
        for record in records:
            segments, _ = model.transcribe(str(record["audio_path"]), **profile.options)
            hypothesis = " ".join(
                segment.text.strip() for segment in segments if segment.text.strip()
            )
            expected_words = _words(record["transcript"])
            hypothesis_words = _words(hypothesis)
            edits += _edit_distance(expected_words, hypothesis_words)
            words += len(expected_words)
            for keyword in record["keywords"]:
                keyword_total += 1
                keyword_hits += _contains_keyword(hypothesis_words, keyword)
        latency = clock() - started
        result = EvaluationMetrics(
            wer=edits / words,
            keyword_accuracy=keyword_hits / keyword_total if keyword_total else 0.0,
            latency_s=latency,
        )
        metrics[profile.name] = result
        profile_results[profile.name] = {
            "model": profile.model,
            "compute_type": "int8",
            "clips": len(records),
            "wer": result.wer,
            "keyword_accuracy": result.keyword_accuracy,
            "latency_s": result.latency_s,
            "latency_per_clip_s": result.latency_s / len(records),
        }
    current = metrics[CURRENT_PROFILE.name]
    gates = {
        profile.name: gate_profile(current, metrics[profile.name])
        for profile in PROFILES[1:]
    }
    passing = [profile for profile in PROFILES[1:] if gates[profile.name]["passed"]]
    recommended = min(passing, key=lambda profile: metrics[profile.name].wer) if passing else CURRENT_PROFILE
    return {
        "manifest_records": len(records),
        "profiles": profile_results,
        "gates": gates,
        "recommended_profile": recommended.name,
        "default_change_allowed": recommended is not CURRENT_PROFILE,
    }


def format_report(report: dict) -> str:
    lines = ["Whisper radio evaluation (50 private clips)"]
    for name, result in report["profiles"].items():
        lines.append(
            f"{name}: WER {result['wer']:.3f}, keywords {result['keyword_accuracy']:.1%}, "
            f"latency {result['latency_s']:.2f}s ({result['latency_per_clip_s']:.2f}s/clip)"
        )
    for name, gate in report["gates"].items():
        latency = f"{gate['latency_ratio']:.2f}x" if gate["latency_ratio"] is not None else "n/a"
        lines.append(
            f"{name} gate: {'PASS' if gate['passed'] else 'FAIL'} "
            f"(WER {gate['relative_wer_improvement']:+.1%}, "
            f"keywords {gate['keyword_point_improvement']:+.1%} points, latency {latency})"
        )
    lines.append(f"default: {report['recommended_profile']}")
    return "\n".join(lines)
