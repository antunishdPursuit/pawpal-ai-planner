from datetime import date, time, timedelta
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pawpal.domain.pawpal_system import Pet, Task, Schedule, ScheduleType, Scheduler


def test_mark_complete_sets_last_completed_date():
    """mark_complete() should set last_completed_date to today."""
    task = Task(
        title="Feed",
        description="Morning kibble",
        assigned_pet_id=1,
        schedule=Schedule(ScheduleType.DAILY, start_date=date.today())
    )
    assert task.last_completed_date is None
    task.mark_complete()
    assert task.last_completed_date == date.today()


def test_add_task_increases_pet_task_count():
    """Adding a task to a pet should increase its task count by 1."""
    pet = Pet(name="Buddy", species="Dog", age=3)
    task = Task(
        title="Walk",
        description="Evening walk",
        assigned_pet_id=pet.pet_id,
        schedule=Schedule(ScheduleType.DAILY, start_date=date.today())
    )
    before = len(pet.get_tasks())
    pet.add_task(task)
    assert len(pet.get_tasks()) == before + 1


# --- Sorting Correctness ---

def test_sort_by_time_returns_chronological_order():
    """Tasks should be returned earliest time first; tasks with no time sort last."""
    pet = Pet(name="Buddy", species="Dog", age=3)
    task_noon = Task(
        title="Lunch",
        description="Midday snack",
        assigned_pet_id=pet.pet_id,
        time_of_day=time(12, 0),
    )
    task_morning = Task(
        title="Feed",
        description="Morning kibble",
        assigned_pet_id=pet.pet_id,
        time_of_day=time(7, 0),
    )
    task_no_time = Task(
        title="Groom",
        description="Brush coat",
        assigned_pet_id=pet.pet_id,
        time_of_day=None,
    )

    sorted_tasks = Scheduler.sort_by_time([task_noon, task_no_time, task_morning])

    assert sorted_tasks[0].title == "Feed"       # 7:00 AM comes first
    assert sorted_tasks[1].title == "Lunch"      # 12:00 PM second
    assert sorted_tasks[2].title == "Groom"      # no time sorts last


# --- Recurrence Logic ---

def test_complete_and_reschedule_creates_next_day_task():
    """Completing a daily task should add a new task due tomorrow to the pet."""
    pet = Pet(name="Whiskers", species="Cat", age=5)
    task = Task(
        title="Feed",
        description="Wet food",
        assigned_pet_id=pet.pet_id,
        schedule=Schedule(ScheduleType.DAILY, start_date=date.today()),
    )
    pet.add_task(task)

    new_task = Scheduler.complete_and_reschedule(task, pet)

    # Original task is marked complete
    assert task.last_completed_date == date.today()
    # A new task was returned and added to the pet
    assert new_task is not None
    assert len(pet.get_tasks()) == 2
    # New task is due tomorrow
    tomorrow = date.today() + timedelta(days=1)
    assert new_task.schedule.next_due_date == tomorrow


# --- Conflict Detection ---

def test_detect_conflicts_flags_same_time_tasks():
    """Two tasks scheduled at the same time should produce a conflict warning."""
    pet = Pet(name="Rex", species="Dog", age=2)
    task_a = Task(
        title="Feed",
        description="Morning kibble",
        assigned_pet_id=pet.pet_id,
        time_of_day=time(8, 0),
    )
    task_b = Task(
        title="Walk",
        description="Morning walk",
        assigned_pet_id=pet.pet_id,
        time_of_day=time(8, 0),
    )

    warnings = Scheduler.detect_conflicts([task_a, task_b], pets=[pet])

    assert len(warnings) == 1
    assert "CONFLICT" in warnings[0]
    assert "08:00 AM" in warnings[0]


def test_detect_conflicts_no_warnings_for_different_times():
    """Tasks at different times should produce no conflict warnings."""
    pet = Pet(name="Rex", species="Dog", age=2)
    task_a = Task(
        title="Feed",
        description="Morning kibble",
        assigned_pet_id=pet.pet_id,
        time_of_day=time(7, 0),
    )
    task_b = Task(
        title="Walk",
        description="Afternoon walk",
        assigned_pet_id=pet.pet_id,
        time_of_day=time(15, 0),
    )

    warnings = Scheduler.detect_conflicts([task_a, task_b], pets=[pet])

    assert warnings == []
