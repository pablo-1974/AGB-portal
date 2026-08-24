"""Validación de nuevas reservas de moscoso."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from db.moscosos_calendar import (
    RESERVABLE_TRIMESTER_1,
    RESERVABLE_TRIMESTER_2,
    RESERVABLE_TRIMESTER_3,
    MoscososDisplayContext,
    buffer_last_booking_date,
    classify_booking_day_kind,
    get_reservable_trimester,
    max_booking_date,
    moscosos_display_day_kind,
)
from db.moscosos_reservations import (
    MAX_RESERVATIONS_PER_DAY,
    MAX_RESERVATIONS_PER_USER_PER_COURSE,
    count_reservations_on_day,
    list_user_reservations,
)

RESERVABLE_KINDS = frozenset(
    {
        RESERVABLE_TRIMESTER_1,
        RESERVABLE_TRIMESTER_2,
        RESERVABLE_TRIMESTER_3,
    }
)

TRIMESTER_KIND_TO_NUM = {
    RESERVABLE_TRIMESTER_1: 1,
    RESERVABLE_TRIMESTER_2: 2,
    RESERVABLE_TRIMESTER_3: 3,
}

TRIMESTER_NUM_LABEL = {
    1: "primer trimestre",
    2: "segundo trimestre",
    3: "tercer trimestre",
}


@dataclass(frozen=True)
class BookingValidationError:
    code: str
    message: str


def staff_other_booking_window(today: date, bundle: dict) -> tuple[date, date]:
    """Ventana al reservar para otro profesor: mañana … último día de clases."""
    min_d = today + timedelta(days=1)
    cal = bundle["calendar"]
    ce = bundle.get("course_end_date")
    last = cal.get("last_day")
    max_d = ce or last
    if ce is not None and last is not None:
        max_d = min(ce, last)
    if max_d is None:
        max_d = min_d
    return min_d, max_d


def trimester_number_for_date(
    d: date,
    cal: dict,
    excluded: set[str],
    *,
    course_start: date | None = None,
    course_end: date | None = None,
) -> int | None:
    kind = get_reservable_trimester(
        d,
        cal,
        excluded,
        course_start=course_start,
        course_end=course_end,
    )
    if kind is None:
        return None
    return TRIMESTER_KIND_TO_NUM.get(kind)


def validate_new_reservation(
    *,
    user_id: int,
    reservation_date: date,
    today: date,
    bundle: dict,
    skip_booking_window: bool = False,
    for_other: bool = False,
) -> BookingValidationError | None:
    cal = bundle["calendar"]
    excluded = bundle["excluded"]
    cal_id = int(cal["id"])
    cs = bundle.get("course_start_date")
    ce = bundle.get("course_end_date")
    already = "Ese profesor ya tiene" if for_other else "Ya tienes"

    ctx = MoscososDisplayContext.build(
        cal,
        excluded,
        buffer_days=bundle["buffer_days"],
        course_start=cs,
        course_end=ce,
    )
    if skip_booking_window:
        if reservation_date <= today:
            return BookingValidationError("past", "Solo se puede reservar en fechas futuras.")
        win_min, win_max = staff_other_booking_window(today, bundle)
        if reservation_date < win_min or reservation_date > win_max:
            return BookingValidationError(
                "not_bookable",
                "Ese día está fuera del curso escolar o no es una fecha futura.",
            )
        kind = moscosos_display_day_kind(reservation_date, ctx)
    else:
        kind = classify_booking_day_kind(reservation_date, today, ctx)
    if kind not in RESERVABLE_KINDS:
        if skip_booking_window:
            return BookingValidationError(
                "not_bookable",
                "Ese día no está disponible para reservar moscoso (consulte el calendario).",
            )
        if reservation_date < today:
            return BookingValidationError("past", "No se puede reservar en fechas pasadas.")
        if reservation_date <= buffer_last_booking_date(today):
            return BookingValidationError(
                "buffer",
                "Ese día aún no está disponible para reservar (plazo de diez días).",
            )
        if reservation_date > max_booking_date(today, ce):
            return BookingValidationError(
                "too_far",
                "Ese día está fuera del plazo de reserva o del calendario lectivo.",
            )
        return BookingValidationError(
            "not_bookable",
            "Ese día no está disponible para reservar moscoso (consulte el calendario).",
        )

    trimester = trimester_number_for_date(
        reservation_date, cal, excluded, course_start=cs, course_end=ce
    )
    if trimester is None:
        return BookingValidationError(
            "not_bookable",
            "Ese día no está disponible para reservar moscoso.",
        )

    existing = list_user_reservations(school_calendar_id=cal_id, user_id=user_id)
    if any(r.reservation_date == reservation_date for r in existing):
        return BookingValidationError(
            "already_day",
            f"{already} una reserva en esa fecha.",
        )

    if len(existing) >= MAX_RESERVATIONS_PER_USER_PER_COURSE:
        return BookingValidationError(
            "course_limit",
            f"{already} las dos reservas permitidas en este curso escolar.",
        )

    if any(r.trimester == trimester for r in existing):
        label = TRIMESTER_NUM_LABEL.get(trimester, "ese trimestre")
        return BookingValidationError(
            "same_trimester",
            f"{already} una reserva en el {label}. Solo se puede reservar un día por trimestre "
            "(dos reservas al curso, en trimestres distintos).",
        )

    if count_reservations_on_day(
        school_calendar_id=cal_id, reservation_date=reservation_date
    ) >= MAX_RESERVATIONS_PER_DAY:
        return BookingValidationError(
            "day_full",
            "Ese día ya tiene dos reservas de otros compañeros. No es posible reservar.",
        )

    return None
