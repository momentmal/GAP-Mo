---
name: change-database-schema
description: How to change the SQLAlchemy data model and generate the matching Alembic migration. Use when adding, removing, or altering fields, tables, or relationships in the database schema.
---

# Change Database Schema

## When to use this

You have modified any of the data models.

## Steps

Make sure that every `model.py` is imported in `src/geo_activity_playground/alembic/env.py`

Create a new alembic revision like so:

```bash
uv run alembic revision --autogenerate -m 'Add Tag.color'
```

Upgrade the schema anchor DB at `database.sqlite` to the latest version.

## Verifying

Verify the schema anchor:

```
❯ sqlite3 database.sqlite 
sqlite> SELECT * FROM alembic_version;
0f02b92c4f94
```

## Pifalls

Don't try to create Alembic migrations without the tooling, the version has will be wrong.

## Reference

See also `docs/change-database-schema.md`.