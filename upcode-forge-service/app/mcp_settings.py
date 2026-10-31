from app.models import Instance


def enabled(db):
    instance = db.get(Instance, 1)
    return bool(instance and instance.mcp_enabled)


def set_enabled(db, value):
    db.get(Instance, 1).mcp_enabled = value
    db.commit()
    return {"enabled": value}
