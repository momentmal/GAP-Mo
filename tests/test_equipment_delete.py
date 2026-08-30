import sqlalchemy

from geo_activity_playground.core.datamodel import DB, Activity, Equipment, Kind


def test_delete_route_removes_equipment_without_activities(client, app):
    with app.app_context():
        equipment = Equipment(name="Spare Bike")
        DB.session.add(equipment)
        DB.session.commit()
        equipment_id = equipment.id

    response = client.post(f"/equipment/{equipment_id}/delete", follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        remaining = DB.session.scalars(
            sqlalchemy.select(Equipment).where(Equipment.id == equipment_id)
        ).all()
        assert remaining == []


def test_delete_route_keeps_equipment_with_activities(client, app):
    with app.app_context():
        equipment = Equipment(name="Bike")
        DB.session.add(equipment)
        DB.session.flush()
        activity = Activity(id=1, name="Ride", kind_id=None, equipment_id=equipment.id)
        DB.session.add(activity)
        DB.session.commit()
        equipment_id = equipment.id

    response = client.post(f"/equipment/{equipment_id}/delete", follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        reloaded = DB.session.get_one(Equipment, equipment_id)
        assert reloaded is not None


def test_delete_route_keeps_equipment_used_as_kind_default(client, app):
    with app.app_context():
        equipment = Equipment(name="Bike")
        DB.session.add(equipment)
        DB.session.flush()
        kind = Kind(name="Cycling", default_equipment_id=equipment.id)
        DB.session.add(kind)
        DB.session.commit()
        equipment_id = equipment.id

    response = client.post(f"/equipment/{equipment_id}/delete", follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        reloaded = DB.session.get_one(Equipment, equipment_id)
        assert reloaded is not None
