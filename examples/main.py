from datetime import date, time
from pawpal.domain.pawpal_system import Owner, Pet, Task, Schedule, ScheduleType, Scheduler


# --- Setup Owner ---
owner = Owner("Jordan")

# --- Create Pets ---
dog = Pet(name="Rex", species="Dog", age=4)
cat = Pet(name="Luna", species="Cat", age=2)
owner.add_pet(dog)
owner.add_pet(cat)

# --- Create Tasks OUT OF ORDER intentionally ---
# Rex's tasks added: evening first, then morning
walk = Task(
    title="Walk",
    description="Evening walk, 20 minutes",
    assigned_pet_id=dog.pet_id,
    schedule=Schedule(ScheduleType.CUSTOM, start_date=date.today(), interval=2),
    time_of_day=time(18, 0)     # 6:00 PM — added first
)
morning_feed = Task(
    title="Morning Feed",
    description="1 cup of dry food",
    assigned_pet_id=dog.pet_id,
    schedule=Schedule(ScheduleType.DAILY, start_date=date.today()),
    time_of_day=time(7, 0)      # 7:00 AM — added second
)
vet_checkup = Task(
    title="Vet Checkup",
    description="Annual vaccination",
    assigned_pet_id=dog.pet_id,
    schedule=Schedule(ScheduleType.DAILY, start_date=date.today()),
    time_of_day=time(14, 0)     # 2:00 PM — added third
)

# Luna's tasks added: grooming first, then feed
grooming = Task(
    title="Grooming",
    description="Brush coat for 5 minutes",
    assigned_pet_id=cat.pet_id,
    schedule=Schedule(ScheduleType.WEEKLY, start_date=date.today()),
    time_of_day=time(10, 0)     # 10:00 AM — added first
)
feed_cat = Task(
    title="Morning Feed",
    description="Half can of wet food",
    assigned_pet_id=cat.pet_id,
    schedule=Schedule(ScheduleType.DAILY, start_date=date.today()),
    time_of_day=time(8, 0)      # 8:00 AM — added second
)

dog.add_task(walk)
dog.add_task(morning_feed)
dog.add_task(vet_checkup)
cat.add_task(grooming)
cat.add_task(feed_cat)

# --- Intentional conflicts for detection demo ---
# Rex and Luna both have something at 8:00 AM
bath_dog = Task(
    title="Bath Time",
    description="Quick rinse after walk",
    assigned_pet_id=dog.pet_id,
    schedule=Schedule(ScheduleType.DAILY, start_date=date.today()),
    time_of_day=time(8, 0)      # conflicts with Luna's Morning Feed at 8:00 AM
)
# Luna has a second task also at 10:00 AM
medicine_cat = Task(
    title="Medicine",
    description="Flea prevention drops",
    assigned_pet_id=cat.pet_id,
    schedule=Schedule(ScheduleType.WEEKLY, start_date=date.today()),
    time_of_day=time(10, 0)     # conflicts with Luna's Grooming at 10:00 AM
)
dog.add_task(bath_dog)
cat.add_task(medicine_cat)

# --- Collect all due tasks across all pets ---
all_due = Scheduler.get_daily_tasks(owner)

# ── Conflict Detection ────────────────────────────────────────────────────
print("=" * 45)
print("  CONFLICT REPORT")
print("=" * 45)
conflicts = Scheduler.detect_conflicts(all_due, pets=owner.pets)
if conflicts:
    for warning in conflicts:
        print(f"  WARNING: {warning}")
else:
    print("  No conflicts detected.")
print()

# ── Demo 1: sort_by_time ──────────────────────────────────────────────────
print("=" * 45)
print(f"  TODAY'S SCHEDULE (sorted) — {date.today()}")
print(f"  Owner: {owner.name}")
print("=" * 45)

sorted_tasks = Scheduler.sort_by_time(all_due)
for task in sorted_tasks:
    d = task.to_display_dict()
    print(f"  [{d['status'].upper():<7}] {d['time_of_day']}  {d['title']}")
    print(f"            {d['description']}")

# ── Demo 2: auto-reschedule on completion ────────────────────────────────
print("\n--- Completing Rex's Morning Feed (DAILY) ---")
Scheduler.complete_and_reschedule(morning_feed, dog)

print("\n--- Completing Rex's Walk (CUSTOM — no new instance expected) ---")
Scheduler.complete_and_reschedule(walk, dog)

print("\n--- Completing Luna's Grooming (WEEKLY) ---")
Scheduler.complete_and_reschedule(grooming, cat)

print("\nRex's full task list after reschedule:")
for t in dog.get_tasks():
    due = str(t.schedule.next_due_date) if t.schedule else "N/A"
    print(f"  {t.title} | due: {due} | status: {t.status}")

print("\nLuna's full task list after reschedule:")
for t in cat.get_tasks():
    due = str(t.schedule.next_due_date) if t.schedule else "N/A"
    print(f"  {t.title} | due: {due} | status: {t.status}")

print("\nToday's pending tasks (any pet):")
all_due = Scheduler.get_daily_tasks(owner, include_completed=True)
pending = Scheduler.filter_tasks(all_due, status="pending")
for t in Scheduler.sort_by_time(pending):
    print(f"  {t.time_of_day}  {t.title} [{t.status}]")

print("\nToday's done tasks (any pet):")
done = Scheduler.filter_tasks(all_due, status="done")
for t in done:
    print(f"  {t.time_of_day}  {t.title} [{t.status}]")

# ── Demo 3: filter by pet name ────────────────────────────────────────────
print("\nOnly Luna's tasks today:")
luna_tasks = Scheduler.filter_tasks(all_due, pet_name="Luna", pets=owner.pets)
for t in Scheduler.sort_by_time(luna_tasks):
    d = t.to_display_dict()
    print(f"  {d['time_of_day']}  {d['title']} [{d['status']}]")

print("\nOnly Rex's pending tasks today:")
rex_pending = Scheduler.filter_tasks(all_due, status="pending", pet_name="Rex", pets=owner.pets)
for t in Scheduler.sort_by_time(rex_pending):
    d = t.to_display_dict()
    print(f"  {d['time_of_day']}  {d['title']} [{d['status']}]")

print("\n" + "=" * 45)
