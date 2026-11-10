from datetime import UTC, date, datetime, time, timedelta

import pytest

from apps.scheduling.models import (
    Appointment,
    AppointmentStatus,
    AvailabilityRule,
    TimeOff,
)
from apps.scheduling.services.slots import candidate_slots, cut_window, free_slots

pytestmark = pytest.mark.django_db

MONDAY = date(2030, 1, 7)  # a Monday; weekday() == 0
NOW = datetime(2030, 1, 1, 0, 0, tzinfo=UTC)  # six days earlier, well inside the window


def utc(day, hour, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)


def add_rule(provider, start, end, weekday=0, **extra):
    return AvailabilityRule.objects.create(
        provider=provider, weekday=weekday, start_time=start, end_time=end, **extra
    )


def starts(slots):
    return [s.start for s in slots]


# ---- the pure helper -------------------------------------------------------------------


def test_cut_window_splits_into_equal_slots():
    slots = cut_window(utc(MONDAY, 3, 30), utc(MONDAY, 5, 30), 30)
    assert len(slots) == 4
    assert slots[0].start == utc(MONDAY, 3, 30)
    assert slots[-1].end == utc(MONDAY, 5, 30)


def test_cut_window_drops_a_partial_slot_at_the_end():
    assert len(cut_window(utc(MONDAY, 9), utc(MONDAY, 10, 20), 30)) == 2


def test_cut_window_shorter_than_one_slot_gives_nothing():
    assert cut_window(utc(MONDAY, 9), utc(MONDAY, 9, 20), 30) == []


# ---- candidate_slots: rules, time off, notice, window ----------------------------------


def test_slots_follow_the_rule_in_the_providers_timezone(make_provider):
    provider = make_provider()  # Asia/Kolkata, UTC+05:30
    add_rule(provider, time(9), time(12))
    slots = candidate_slots(provider, MONDAY, now=NOW)
    assert len(slots) == 6
    assert slots[0].start == utc(MONDAY, 3, 30)  # 09:00 IST
    assert slots[-1].end == utc(MONDAY, 6, 30)  # 12:00 IST


def test_timezone_is_not_hardcoded(make_provider):
    provider = make_provider(timezone="America/New_York")  # UTC-05:00 in January
    add_rule(provider, time(9), time(10))
    slots = candidate_slots(provider, MONDAY, now=NOW)
    assert starts(slots) == [utc(MONDAY, 14), utc(MONDAY, 14, 30)]


def test_daylight_saving_shifts_the_utc_time(make_provider):
    provider = make_provider(timezone="America/New_York")
    sunday = date(2030, 3, 10)  # US clocks go forward on this Sunday
    add_rule(provider, time(9), time(10), weekday=6)
    slots = candidate_slots(provider, sunday, now=datetime(2030, 3, 1, tzinfo=UTC))
    assert slots[0].start == utc(sunday, 13)  # 09:00 EDT is UTC-4, not UTC-5


def test_day_without_a_rule_has_no_slots(make_provider):
    provider = make_provider()
    add_rule(provider, time(9), time(12), weekday=1)  # Tuesday only
    assert candidate_slots(provider, MONDAY, now=NOW) == []


def test_two_windows_leave_a_gap_for_lunch(make_provider):
    provider = make_provider()
    add_rule(provider, time(9), time(10))
    add_rule(provider, time(14), time(15))
    assert len(candidate_slots(provider, MONDAY, now=NOW)) == 4


def test_rule_outside_its_validity_dates_is_ignored(make_provider):
    provider = make_provider()
    add_rule(provider, time(9), time(10), valid_from=date(2030, 2, 1))
    add_rule(provider, time(11), time(12), valid_to=date(2030, 1, 1))
    assert candidate_slots(provider, MONDAY, now=NOW) == []


def test_time_off_removes_overlapping_slots(make_provider):
    provider = make_provider()
    add_rule(provider, time(9), time(12))
    TimeOff.objects.create(  # 10:00-11:00 IST
        provider=provider, starts_at=utc(MONDAY, 4, 30), ends_at=utc(MONDAY, 5, 30)
    )
    slots = candidate_slots(provider, MONDAY, now=NOW)
    assert len(slots) == 4
    assert utc(MONDAY, 4, 30) not in starts(slots)
    assert utc(MONDAY, 5, 0) not in starts(slots)


def test_minimum_notice_drops_slots_that_are_too_soon(make_provider):
    provider = make_provider(min_notice_hours=2)
    add_rule(provider, time(9), time(12))  # first slot 03:30 UTC
    now = utc(MONDAY, 2, 0)  # earliest bookable start is 04:00 UTC
    slots = candidate_slots(provider, MONDAY, now=now)
    assert slots[0].start == utc(MONDAY, 4)
    assert len(slots) == 5


def test_nothing_is_offered_beyond_the_booking_window(make_provider):
    provider = make_provider(booking_window_days=30)
    add_rule(provider, time(9), time(12))
    far_monday = date(2030, 3, 4)  # more than 30 days after NOW
    assert candidate_slots(provider, far_monday, now=NOW) == []


def test_past_days_have_no_slots(make_provider):
    provider = make_provider()
    add_rule(provider, time(9), time(12))
    assert candidate_slots(provider, MONDAY, now=utc(MONDAY, 12)) == []


# ---- free_slots: also subtracts bookings -----------------------------------------------


def book(provider, client, start, status=AppointmentStatus.BOOKED):
    return Appointment.objects.create(
        provider=provider,
        client=client,
        starts_at=start,
        ends_at=start + timedelta(minutes=30),
        status=status,
    )


def test_booked_slot_is_not_free(make_provider, make_user):
    provider = make_provider()
    add_rule(provider, time(9), time(12))
    book(provider, make_user(), utc(MONDAY, 3, 30))
    free = free_slots(provider, MONDAY, now=NOW)
    assert len(free) == 5
    assert utc(MONDAY, 3, 30) not in starts(free)
    # candidate_slots deliberately ignores bookings: the database decides conflicts
    assert len(candidate_slots(provider, MONDAY, now=NOW)) == 6


def test_cancelled_booking_does_not_block_a_slot(make_provider, make_user):
    provider = make_provider()
    add_rule(provider, time(9), time(12))
    book(provider, make_user(), utc(MONDAY, 3, 30), status=AppointmentStatus.CANCELLED)
    assert len(free_slots(provider, MONDAY, now=NOW)) == 6


def test_another_providers_booking_does_not_matter(make_provider, make_user):
    provider, other = make_provider(), make_provider()
    add_rule(provider, time(9), time(12))
    book(other, make_user(), utc(MONDAY, 3, 30))
    assert len(free_slots(provider, MONDAY, now=NOW)) == 6


def test_free_slots_uses_a_fixed_number_of_queries(
    make_provider, make_user, django_assert_num_queries
):
    provider = make_provider()
    add_rule(provider, time(9), time(17))  # 16 slots
    client = make_user()
    for hour in (4, 5, 6):
        book(provider, client, utc(MONDAY, hour))
    with django_assert_num_queries(3):  # rules, time off, appointments, whatever the day holds
        free_slots(provider, MONDAY, now=NOW)
from datetime import UTC, date, datetime, time, timedelta

import pytest

from apps.scheduling.models import (
    Appointment,
    AppointmentStatus,
    AvailabilityRule,
    TimeOff,
)
from apps.scheduling.services.slots import candidate_slots, cut_window, free_slots

pytestmark = pytest.mark.django_db

MONDAY = date(2030, 1, 7)  # a Monday; weekday() == 0
NOW = datetime(2030, 1, 1, 0, 0, tzinfo=UTC)  # six days earlier, well inside the window


def utc(day, hour, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)


def add_rule(provider, start, end, weekday=0, **extra):
    return AvailabilityRule.objects.create(
        provider=provider, weekday=weekday, start_time=start, end_time=end, **extra
    )


def starts(slots):
    return [s.start for s in slots]


# ---- the pure helper -------------------------------------------------------------------


def test_cut_window_splits_into_equal_slots():
    slots = cut_window(utc(MONDAY, 3, 30), utc(MONDAY, 5, 30), 30)
    assert len(slots) == 4
    assert slots[0].start == utc(MONDAY, 3, 30)
    assert slots[-1].end == utc(MONDAY, 5, 30)


def test_cut_window_drops_a_partial_slot_at_the_end():
    assert len(cut_window(utc(MONDAY, 9), utc(MONDAY, 10, 20), 30)) == 2


def test_cut_window_shorter_than_one_slot_gives_nothing():
    assert cut_window(utc(MONDAY, 9), utc(MONDAY, 9, 20), 30) == []


# ---- candidate_slots: rules, time off, notice, window ----------------------------------


def test_slots_follow_the_rule_in_the_providers_timezone(make_provider):
    provider = make_provider()  # Asia/Kolkata, UTC+05:30
    add_rule(provider, time(9), time(12))
    slots = candidate_slots(provider, MONDAY, now=NOW)
    assert len(slots) == 6
    assert slots[0].start == utc(MONDAY, 3, 30)  # 09:00 IST
    assert slots[-1].end == utc(MONDAY, 6, 30)  # 12:00 IST


def test_timezone_is_not_hardcoded(make_provider):
    provider = make_provider(timezone="America/New_York")  # UTC-05:00 in January
    add_rule(provider, time(9), time(10))
    slots = candidate_slots(provider, MONDAY, now=NOW)
    assert starts(slots) == [utc(MONDAY, 14), utc(MONDAY, 14, 30)]


def test_daylight_saving_shifts_the_utc_time(make_provider):
    provider = make_provider(timezone="America/New_York")
    sunday = date(2030, 3, 10)  # US clocks go forward on this Sunday
    add_rule(provider, time(9), time(10), weekday=6)
    slots = candidate_slots(provider, sunday, now=datetime(2030, 3, 1, tzinfo=UTC))
    assert slots[0].start == utc(sunday, 13)  # 09:00 EDT is UTC-4, not UTC-5


def test_day_without_a_rule_has_no_slots(make_provider):
    provider = make_provider()
    add_rule(provider, time(9), time(12), weekday=1)  # Tuesday only
    assert candidate_slots(provider, MONDAY, now=NOW) == []


def test_two_windows_leave_a_gap_for_lunch(make_provider):
    provider = make_provider()
    add_rule(provider, time(9), time(10))
    add_rule(provider, time(14), time(15))
    assert len(candidate_slots(provider, MONDAY, now=NOW)) == 4


def test_rule_outside_its_validity_dates_is_ignored(make_provider):
    provider = make_provider()
    add_rule(provider, time(9), time(10), valid_from=date(2030, 2, 1))
    add_rule(provider, time(11), time(12), valid_to=date(2030, 1, 1))
    assert candidate_slots(provider, MONDAY, now=NOW) == []


def test_time_off_removes_overlapping_slots(make_provider):
    provider = make_provider()
    add_rule(provider, time(9), time(12))
    TimeOff.objects.create(  # 10:00-11:00 IST
        provider=provider, starts_at=utc(MONDAY, 4, 30), ends_at=utc(MONDAY, 5, 30)
    )
    slots = candidate_slots(provider, MONDAY, now=NOW)
    assert len(slots) == 4
    assert utc(MONDAY, 4, 30) not in starts(slots)
    assert utc(MONDAY, 5, 0) not in starts(slots)


def test_minimum_notice_drops_slots_that_are_too_soon(make_provider):
    provider = make_provider(min_notice_hours=2)
    add_rule(provider, time(9), time(12))  # first slot 03:30 UTC
    now = utc(MONDAY, 2, 0)  # earliest bookable start is 04:00 UTC
    slots = candidate_slots(provider, MONDAY, now=now)
    assert slots[0].start == utc(MONDAY, 4)
    assert len(slots) == 5


def test_nothing_is_offered_beyond_the_booking_window(make_provider):
    provider = make_provider(booking_window_days=30)
    add_rule(provider, time(9), time(12))
    far_monday = date(2030, 3, 4)  # more than 30 days after NOW
    assert candidate_slots(provider, far_monday, now=NOW) == []


def test_past_days_have_no_slots(make_provider):
    provider = make_provider()
    add_rule(provider, time(9), time(12))
    assert candidate_slots(provider, MONDAY, now=utc(MONDAY, 12)) == []


# ---- free_slots: also subtracts bookings -----------------------------------------------


def book(provider, client, start, status=AppointmentStatus.BOOKED):
    return Appointment.objects.create(
        provider=provider,
        client=client,
        starts_at=start,
        ends_at=start + timedelta(minutes=30),
        status=status,
    )


def test_booked_slot_is_not_free(make_provider, make_user):
    provider = make_provider()
    add_rule(provider, time(9), time(12))
    book(provider, make_user(), utc(MONDAY, 3, 30))
    free = free_slots(provider, MONDAY, now=NOW)
    assert len(free) == 5
    assert utc(MONDAY, 3, 30) not in starts(free)
    # candidate_slots deliberately ignores bookings: the database decides conflicts
    assert len(candidate_slots(provider, MONDAY, now=NOW)) == 6


def test_cancelled_booking_does_not_block_a_slot(make_provider, make_user):
    provider = make_provider()
    add_rule(provider, time(9), time(12))
    book(provider, make_user(), utc(MONDAY, 3, 30), status=AppointmentStatus.CANCELLED)
    assert len(free_slots(provider, MONDAY, now=NOW)) == 6


def test_another_providers_booking_does_not_matter(make_provider, make_user):
    provider, other = make_provider(), make_provider()
    add_rule(provider, time(9), time(12))
    book(other, make_user(), utc(MONDAY, 3, 30))
    assert len(free_slots(provider, MONDAY, now=NOW)) == 6


def test_free_slots_uses_a_fixed_number_of_queries(
    make_provider, make_user, django_assert_num_queries
):
    provider = make_provider()
    add_rule(provider, time(9), time(17))  # 16 slots
    client = make_user()
    for hour in (4, 5, 6):
        book(provider, client, utc(MONDAY, hour))
    with django_assert_num_queries(3):  # rules, time off, appointments, whatever the day holds
        free_slots(provider, MONDAY, now=NOW)
