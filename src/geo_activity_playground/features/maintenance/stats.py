import datetime

import pandas as pd
import sqlalchemy as sa

from ...core.datamodel import DB, Equipment
from .model import MaintenanceAction, RecurringTask


def get_maintenance_actions_table() -> pd.DataFrame:
    rows = DB.session.execute(
        sa.select(
            MaintenanceAction.id,
            MaintenanceAction.title,
            MaintenanceAction.date,
            MaintenanceAction.usage_km,
            MaintenanceAction.cost,
            Equipment.name.label("equipment"),
        ).join(MaintenanceAction.equipment)
    ).all()
    df = pd.DataFrame(
        rows, columns=["id", "title", "date", "usage_km", "cost", "equipment"]
    )
    if len(df):
        df["date"] = pd.to_datetime(df["date"])
        df["year"] = df["date"].dt.year
        df["cost"] = df["cost"].astype(float)
    return df


def get_cost_by_equipment(actions: pd.DataFrame) -> pd.DataFrame:
    summary = (
        actions.groupby("equipment")
        .agg(total_cost=("cost", "sum"), num_actions=("id", "count"))
        .reset_index()
        .sort_values("total_cost", ascending=False)
    )
    equipments = DB.session.scalars(sa.select(Equipment)).all()
    usage = pd.DataFrame(
        {
            "equipment": equipment.name,
            "total_distance_km": equipment.total_distance_km,
        }
        for equipment in equipments
    )
    return summary.merge(usage, on="equipment", how="left")


def get_maintenance_flow_by_title(actions: pd.DataFrame) -> pd.DataFrame:
    return (
        actions.groupby(["equipment", "title"])["cost"].sum().reset_index(name="cost")
    )


def get_due_tasks() -> list[RecurringTask]:
    tasks = DB.session.scalars(sa.select(RecurringTask)).all()
    due = [task for task in tasks if task.is_overdue(task.equipment.total_distance_km)]
    return sorted(due, key=lambda task: (task.equipment.name, task.title))


def get_task_progress(
    task: RecurringTask, current_km: float, now: datetime.date | None = None
) -> float | None:
    """Fraction of the task's interval that is used up, or None if unmeasurable.

    A task with both a distance and a time interval is as far along as the more
    advanced of the two. Values above one mean the task is overdue.
    """
    last = task.last_execution
    if last is None:
        return None
    now = now or datetime.date.today()
    fractions = []
    if task.interval_km and last.usage_km is not None:
        fractions.append((current_km - last.usage_km) / task.interval_km)
    if task.interval_days:
        fractions.append((now - last.date).days / task.interval_days)
    return max(fractions) if fractions else None


def get_next_task(equipment: Equipment) -> tuple[RecurringTask, float] | None:
    """The recurring task of this equipment that is closest to being due."""
    current_km = equipment.total_distance_km
    rated = [
        (task, progress)
        for task in equipment.recurring_tasks
        if (progress := get_task_progress(task, current_km)) is not None
    ]
    if not rated:
        return None
    return max(rated, key=lambda pair: pair[1])
