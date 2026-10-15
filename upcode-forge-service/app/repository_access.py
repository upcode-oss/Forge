from fastapi import HTTPException
from sqlalchemy import exists, or_, select

from app.models import Membership, Organization, OrganizationMember, Repository, User
from app.organization_access import member_role

LEVELS = {"read": 1, "write": 2, "maintain": 3}
ORGANIZATION_ROLES = {"owner": "maintain", "maintainer": "maintain", "reader": "read"}


def public_repositories():
    return (Repository.visibility == "public") & or_(
        Repository.organization_id.is_(None),
        exists()
        .where(Organization.id == Repository.organization_id, Organization.visibility == "public")
        .correlate(Repository),
    )


def visible(user, *, admin_access=True):
    if user is None:
        return public_repositories()
    member = (
        exists()
        .where(
            OrganizationMember.organization_id == Repository.organization_id,
            OrganizationMember.user_id == user.id,
        )
        .correlate(Repository)
    )
    organization_visible = or_(
        Repository.organization_id.is_(None),
        exists()
        .where(Organization.id == Repository.organization_id, Organization.visibility == "public")
        .correlate(Repository),
        member,
    )
    rights = (
        True
        if user.is_admin and admin_access
        else or_(
            public_repositories(),
            Repository.owner_id == user.id,
            member,
            exists()
            .where(Membership.repository_id == Repository.id, Membership.user_id == user.id)
            .correlate(Repository),
        )
    )
    return organization_visible & rights


def role(db, repo, user):
    organization = db.get(Organization, repo.organization_id) if repo.organization_id else None
    inherited = member_role(db, organization.id, user) if organization else None
    if organization and organization.visibility == "private" and inherited is None:
        return None
    if user and (user.is_admin or repo.owner_id == user.id):
        return "maintain"
    grants = ["read"] if repo.visibility == "public" else []
    if inherited:
        grants.append(ORGANIZATION_ROLES[inherited])
    if user:
        direct = db.scalar(
            select(Membership.role).where(
                Membership.repository_id == repo.id, Membership.user_id == user.id
            )
        )
        if direct:
            grants.append(direct)
    return max(grants, key=LEVELS.get) if grants else None


def access(db, repo_id, user, level="read"):
    repo = db.get(Repository, repo_id)
    permission = role(db, repo, user) if repo else None
    if not permission:
        raise HTTPException(404, "Repository not found")
    if LEVELS[permission] < LEVELS[level]:
        raise HTTPException(403, "Insufficient repository permissions")
    return repo


def find_repository(db, owner, name):
    if owner.startswith("organizations/"):
        return db.scalar(
            select(Repository)
            .join(Organization, Organization.id == Repository.organization_id)
            .where(
                Organization.slug == owner.removeprefix("organizations/"), Repository.name == name
            )
        )
    return db.scalar(
        select(Repository)
        .join(User, User.id == Repository.owner_id)
        .where(User.username == owner, Repository.name == name)
    )
