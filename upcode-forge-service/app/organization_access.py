from threading import RLock

from fastapi import HTTPException
from sqlalchemy import exists, or_, select

from app.models import Organization, OrganizationMember

# The supported deployment uses one worker; SQLite does not implement row locks.
mutation_lock = RLock()


def member_role(db, organization_id, user, *, lock=False):
    if user is None:
        return None
    query = select(OrganizationMember.role).where(
        OrganizationMember.organization_id == organization_id,
        OrganizationMember.user_id == user.id,
    )
    return db.scalar(query.with_for_update() if lock else query)


def visible_to(user):
    if user is None:
        return Organization.visibility == "public"
    return or_(
        Organization.visibility == "public",
        exists()
        .where(
            OrganizationMember.organization_id == Organization.id,
            OrganizationMember.user_id == user.id,
        )
        .correlate(Organization),
    )


def access(db, slug, user, *, edit=False, lock=False):
    query = select(Organization).where(Organization.slug == slug.lower())
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    organization = db.scalar(query)
    role = member_role(db, organization.id, user, lock=lock) if organization else None
    if organization is None or (organization.visibility == "private" and role is None):
        raise HTTPException(404, "Organization not found")
    if edit and role not in ("owner", "maintainer"):
        raise HTTPException(403, "Owner or Maintainer access required")
    return organization, role
