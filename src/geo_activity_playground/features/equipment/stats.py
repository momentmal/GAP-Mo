import dataclasses
import datetime

import pandas as pd
import sqlalchemy as sa

from ...core.datamodel import DB, Activity, Equipment
from ..maintenance.model import RecurringTask
from ..maintenance.stats import get_next_task


def get_equipment_use_table(
    activity_meta: pd.DataFrame, offsets: dict[str, float]
) -> pd.DataFrame:
    result = activity_meta.groupby("equipment").apply(
        lambda group: pd.Series(
            {
                "total_distance_km": group["distance_km"].sum(),
                "first_use": group["start_local"].min(skipna=True),
                "last_use": group["start_local"].max(skipna=True),
            },
        ),
        include_groups=False,
    )
    # Equipment without any activities (e.g. newly added, or "Unknown" once
    # every activity has been assigned) is absent from the groupby result but
    # may still carry an offset, so make sure it has a row too.
    result = result.reindex(result.index.union(offsets.keys()))
    result["total_distance_km"] = result["total_distance_km"].fillna(0.0)
    for equipment, offset in offsets.items():
        result.loc[equipment, "total_distance_km"] += offset

    result = result.sort_values("last_use", ascending=False)
    result["total_distance_km"] = [
        int(round(elem)) for elem in result["total_distance_km"]
    ]
    result["first_use"] = [
        date.date().isoformat() if pd.notna(date) else ""
        for date in result["first_use"]
    ]
    result["last_use"] = [
        date.date().isoformat() if pd.notna(date) else "" for date in result["last_use"]
    ]

    return result.reset_index()


@dataclasses.dataclass
class EquipmentStatus:
    equipment: Equipment
    total_distance_km: float
    last_use: datetime.date | None
    next_task: RecurringTask | None
    next_task_progress: float | None


def get_equipment_status(
    recently_used_days: int = 90, limit: int | None = None
) -> list[EquipmentStatus]:
    """Equipment used recently, most recently used first, with maintenance progress."""
    cutoff = datetime.date.today() - datetime.timedelta(days=recently_used_days)
    statuses = []
    for equipment in DB.session.scalars(sa.select(Equipment)):
        last_use = DB.session.execute(
            sa.select(sa.func.max(Activity.start)).where(
                Activity.equipment_id == equipment.id
            )
        ).scalar()
        last_use = last_use.date() if last_use else None
        if last_use is None or last_use < cutoff:
            continue
        next_task = get_next_task(equipment)
        statuses.append(
            EquipmentStatus(
                equipment=equipment,
                total_distance_km=equipment.total_distance_km,
                last_use=last_use,
                next_task=next_task[0] if next_task else None,
                next_task_progress=next_task[1] if next_task else None,
            )
        )
    statuses.sort(key=lambda status: status.last_use, reverse=True)
    return statuses[:limit] if limit else statuses
