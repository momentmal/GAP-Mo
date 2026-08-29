import pandas as pd

from geo_activity_playground.features.equipment.stats import get_equipment_use_table


def test_get_equipment_use_table_handles_equipment_without_activities():
    meta = pd.DataFrame(
        {
            "equipment": ["Bike"],
            "distance_km": [10.0],
            "start_local": [pd.Timestamp("2026-01-01")],
        }
    )
    offsets = {"Bike": 5.0, "Unknown": 0.0}

    result = get_equipment_use_table(meta, offsets)

    row_by_equipment = {row.equipment: row for row in result.itertuples()}
    assert row_by_equipment["Bike"].total_distance_km == 15
    assert row_by_equipment["Bike"].first_use == "2026-01-01"
    assert row_by_equipment["Unknown"].total_distance_km == 0
    assert row_by_equipment["Unknown"].first_use == ""
    assert row_by_equipment["Unknown"].last_use == ""
