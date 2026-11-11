"""Explicitly add fictional presentation data; never run during app startup."""
import argparse
from datetime import date, time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pawpal.domain.pawpal_system import Owner, Pet, Task
from pawpal.domain.planner_storage import PlannerStore
from pawpal.domain.task_contract import TaskDraft


DEMO_WEEK = date(2026, 11, 16)
PROFILES = (
    ("Alex Rivera (demo)", (("Luna", "dog", 3), ("Milo", "cat", 2))),
    ("Jordan Lee (demo)", (("Mochi", "dog", 4), ("Olive", "cat", 5))),
    ("Sam Taylor (demo)", (("Pepper", "dog", 2),)),
)
# Owner index, pet name, November day, local time, title, description, location.
TASKS = (
    (0, "Luna", 16, "09:00", "Morning park walk", "Take Luna for a relaxed walk.", "Riverside Park"),
    (0, "Milo", 16, "17:00", "Brush Milo's coat", "A gentle brush and a few treats.", "Home"),
    (1, "Mochi", 17, "10:00", "Practice recall", "A short training session with Mochi's favorite toy.", "Riverside Park"),
    (0, "Luna", 18, "09:00", "Walk Luna", "Take Luna to the park before the afternoon gets busy.", "Riverside Park"),
    (2, "Pepper", 18, "15:00", "Puzzle toy time", "Set up Pepper's treat puzzle for an enrichment break.", "Home"),
    (1, "Olive", 19, "12:00", "Play with Olive", "Bring out the feather wand for a short play session.", "Home"),
    (0, "Milo", 20, "11:00", "Refresh litter tray", "Clean Milo's tray and top up the litter.", "Home"),
    (1, "Mochi", 20, "16:00", "Brush Mochi", "Brush out Mochi's coat after the afternoon walk.", "Home"),
    (2, "Pepper", 21, "10:00", "Weekend sniff walk", "Let Pepper explore at an easy pace.", "Riverside Park"),
    (1, "Olive", 22, "14:00", "Clean water fountain", "Wash Olive's fountain and refill it with fresh water.", "Home"),
)


def request_id(index):
    return str(uuid5(NAMESPACE_URL, f"https://pawpal.local/demo/{DEMO_WEEK}/{index}"))


def seed_demo(store: PlannerStore) -> bool:
    """Add all records atomically, or skip a previously loaded set without edits."""
    ids = [request_id(i) for i in range(len(TASKS))]
    with store.transaction() as conn:
        present = {row[0] for row in conn.execute(
            f"SELECT creation_request_id FROM task WHERE creation_request_id IN ({','.join('?' for _ in ids)})", ids)}
        if present == set(ids):
            return False
        names = {row[0].casefold() for row in conn.execute("SELECT name FROM owner")}
        if present or any(name.casefold() in names for name, _ in PROFILES):
            raise ValueError("Demo data already exists or was changed. No records were added or replaced.")
        store._reserve_ids(conn)
        owners = []
        for name, pets in PROFILES:
            owner = Owner(name, "America/New_York")
            for pet_name, species, age in pets:
                owner.add_pet(Pet(pet_name, species, age))
            owners.append(owner)
        for index, (who, pet_name, day, at, title, description, location) in enumerate(TASKS):
            owner = owners[who]
            pet = next(pet for pet in owner.pets if pet.name == pet_name)
            draft = TaskDraft(pet.pet_id, title, date(2026, 11, day), time.fromisoformat(at),
                              description=description, location=location, request_id=ids[index]).validate(owner)
            pet.add_task(Task(draft.title, draft.description, pet.pet_id,
                              one_off_due_date=draft.due_date, time_of_day=draft.time_of_day,
                              location_text=draft.location, creation_request_id=draft.request_id))
        for owner in owners:
            store._save(conn, owner)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, help="Optional separate SQLite database; defaults to the app's database.")
    args = parser.parse_args()
    try:
        added = seed_demo(PlannerStore(args.database))
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    print("Added 3 demo users, 5 pets and 10 tasks for November 16–22, 2026."
          if added else "Demo data is already loaded; no records changed.")
