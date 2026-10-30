"""The overlay: per-question calls on top of the frozen draft-5 cases.

Editing a member case mints a new uid and drops it from draft-5, so what
the plain baseline needs to know beyond the case lives here, keyed by uid,
and AJ reviews it before the pilot. A question the overlay does not list
takes the defaults: its text applies to any assistant, a decline is not a
right answer, and its figure checks gate.

- ``text``: ``any``, or ``horizon_only`` when the expected text describes
  Horizon's own limits ("explains the concession limit"); then it is
  reported but does not gate, for either assistant.
- ``decline_right``: a decline (or a question back) is the right answer.
- ``figure_info_only``: a fair reply could state a different figure (an
  open parameter), so the figure checks are reported but do not gate.
- ``areas``: pins an area id's source where the reference guessed wrong.
- ``why``: one line, for the reviewer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from goldset.groundtruth.catalog import AOI_TYPES

SCHEMA_VERSION = 1
TEXT_VALUES = ("any", "horizon_only")
KEYS = {"id", "text", "decline_right", "figure_info_only", "areas", "why"}
SOURCES = tuple(AOI_TYPES)


@dataclass(frozen=True)
class Calls:
    text: str = "any"
    decline_right: bool = False
    figure_info_only: bool = False
    areas: tuple[tuple[str, str], ...] = ()


def calls_from(entry: dict[str, Any]) -> Calls:
    unknown = set(entry) - KEYS
    if unknown:
        raise ValueError(f"{entry.get('id', '?')}: unknown overlay keys {sorted(unknown)}")
    text = entry.get("text", "any")
    if text not in TEXT_VALUES:
        raise ValueError(f"{entry.get('id', '?')}: text must be one of {TEXT_VALUES}")
    areas = entry.get("areas") or {}
    bad = [s for s in areas.values() if s not in SOURCES]
    if bad:
        raise ValueError(f"{entry.get('id', '?')}: unknown area sources {bad}")
    return Calls(
        text=text,
        decline_right=bool(entry.get("decline_right", False)),
        figure_info_only=bool(entry.get("figure_info_only", False)),
        areas=tuple(sorted(areas.items())),
    )


def load(path: Path, members: set[str]) -> tuple[dict[str, Any], dict[str, Calls]]:
    """The overlay's header and its calls by uid. Fails loudly on a uid that
    is not a member: a stale overlay must not silently stop applying."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{path}: schema_version must be {SCHEMA_VERSION}")
    questions = data.get("questions") or {}
    strangers = set(questions) - members
    if strangers:
        raise ValueError(f"{path}: {len(strangers)} uids are not draft-5 members")
    header = {k: v for k, v in data.items() if k != "questions"}
    return header, {uid: calls_from(entry) for uid, entry in questions.items()}
