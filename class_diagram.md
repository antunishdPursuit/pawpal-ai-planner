# PawPal+ Class Diagram

The diagram matches the current implementation in `pawpal_system.py`.
The required Mermaid source is [diagrams/uml_final.mmd](diagrams/uml_final.mmd).
The [historical PNG](assets/uml_final.png) is an earlier diagram; use this source for the current design.

```mermaid
classDiagram
    class ScheduleType {
        <<enumeration>>
        DAILY
        WEEKLY
        CUSTOM
    }
    class Schedule {
        +ScheduleType schedule_type
        +date start_date
        +int interval
        +date next_due_date
        +calculate_next_due_date() date
        +is_due_today() bool
    }
    class Task {
        +int task_id
        +str title
        +str description
        +int assigned_pet_id
        +Schedule schedule
        +time time_of_day
        +date last_completed_date
        +status str
        +mark_complete() bool
        +update_task(title, description, schedule)
        +next_occurrence() Task
        +to_display_dict() dict
    }
    class Pet {
        +int pet_id
        +str name
        +str species
        +int age
        +list~Task~ tasks
        +add_task(task)
        +remove_task(task_id)
        +get_tasks() list~Task~
        +get_tasks_by_status(status) list~Task~
        +get_due_tasks_today() list~Task~
    }
    class Owner {
        +int owner_id
        +str name
        +list~Pet~ pets
        +add_pet(pet)
        +remove_pet(pet_id)
        +find_pet(pet_id) Pet
        +get_pet(pet_id) Pet
        +get_tasks_for_pet(pet_id, status) list~Task~
        +get_all_tasks() list~Task~
        +view_daily_plan()
    }
    class Scheduler {
        <<utility>>
        +get_daily_tasks(owner, include_completed) list~Task~$
        +sort_by_time(tasks) list~Task~$
        +complete_and_reschedule(task, pet) Task$
        +detect_conflicts(tasks, pets) list~str~$
        +filter_tasks(tasks, status, pet_name, pets) list~Task~$
    }
    Owner "1" --> "0..*" Pet : owns
    Pet "1" --> "0..*" Task : stores occurrences
    Task "1" --> "0..1" Schedule : follows
    Schedule --> ScheduleType : uses
    Scheduler ..> Owner : reads get_all_tasks
    Scheduler ..> Pet : adds next occurrence
    Scheduler ..> Task : schedules
    note for Task "schedule, time_of_day, and last_completed_date can be None. Completed daily/weekly occurrences stay done."
    note for Schedule "CUSTOM routines advance in place; DAILY and WEEKLY create new Task occurrences through Scheduler."
```
