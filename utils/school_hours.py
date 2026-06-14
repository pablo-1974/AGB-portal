"""Máscara de horas lectivas (1ª–6ª + recreo), compartida con ausencias y extraescolares."""

from __future__ import annotations

HOUR_LABELS = ("1ª", "2ª", "3ª", "Recreo", "4ª", "5ª", "6ª")
FULL_DAY_MASK = (1 << 7) - 1


def hours_mask_from_form(mode: str, hour_from: int | None, hour_to: int | None) -> int | None:
    m = (mode or "all").strip().lower()
    if m == "all":
        return FULL_DAY_MASK
    if hour_from is None or hour_to is None:
        return None
    low = min(int(hour_from), int(hour_to))
    high = max(int(hour_from), int(hour_to))
    if low < 0 or high > 6:
        return None
    mask = 0
    for idx in range(low, high + 1):
        mask |= 1 << idx
    return mask


def mask_to_human(mask: int) -> str:
    if mask <= 0:
        return "—"
    if mask == FULL_DAY_MASK:
        return "Todas"
    on = [i for i in range(7) if (mask >> i) & 1]
    if not on:
        return "—"
    parts: list[str] = []
    start = on[0]
    prev = on[0]
    for idx in on[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        parts.append(
            HOUR_LABELS[start] if start == prev else f"{HOUR_LABELS[start]}-{HOUR_LABELS[prev]}"
        )
        start = prev = idx
    parts.append(
        HOUR_LABELS[start] if start == prev else f"{HOUR_LABELS[start]}-{HOUR_LABELS[prev]}"
    )
    return ", ".join(parts)
