"""Validación de nuevas reservas de moscoso."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from db.moscosos_calendar import (
    RESERVABLE_TRIMESTER_1,
    RESERVABLE_TRIMESTER_2,
    RESERVABLE_TRIMESTER_3,
    MoscososDisplayContext,
    buffer_last_booking_date,
    classify_booking_day_kind,
    get_reservable_trimester,
    max_booking_date,
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
) -> BookingValidationError | None:
    cal = bundle["calendar"]
    excluded = bundle["excluded"]
    cal_id = int(cal["id"])
    cs = bundle.get("course_start_date")
    ce = bundle.get("course_end_date")

    ctx = MoscososDisplayContext.build(
        cal,
        excluded,
        buffer_days=bundle["buffer_days"],
        course_start=cs,
        course_end=ce,
    )
    kind = classify_booking_day_kind(reservation_date, today, ctx)
    if kind not in RESERVABLE_KINDS:
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
            "Ya tienes una reserva en esa fecha.",
        )

    if len(existing) >= MAX_RESERVATIONS_PER_USER_PER_COURSE:
        return BookingValidationError(
            "course_limit",
            "Ya tienes las dos reservas permitidas en este curso escolar.",
        )

    if any(r.trimester == trimester for r in existing):
        label = TRIMESTER_NUM_LABEL.get(trimester, "ese trimestre")
        return BookingValidationError(
            "same_trimester",
            f"Ya tienes una reserva en el {label}. Solo puedes reservar un día por trimestre "
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
