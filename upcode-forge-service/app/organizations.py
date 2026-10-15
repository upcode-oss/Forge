import hashlib
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api import attribute, repo_data
from app.avatars import avatar_url, read_avatar
from app.database import get_db
from app.models import Organization, OrganizationMember, Repository, User
from app.organization_access import access, member_role, mutation_lock, visible_to
from app.repository_access import visible as repositories_visible
from app.schemas import OrganizationCreate, OrganizationMemberInput, OrganizationUpdate
from app.security import current_user, optional_user, throttle

router = APIRouter(prefix="/api/v1/organizations")


def organization_data(db, organization, viewer):
    return {
        **{
            key: attribute(organization, key)
            for key in ("id", "slug", "name", "description", "visibility", "created_at")
        },
        "avatar_url": (
            f"/api/v1/organizations/{organization.slug}/avatar/{organization.avatar_digest}.png"
            if organization.avatar_digest
            else None
        ),
        "role": member_role(db, organization.id, viewer),
        "member_count": db.scalar(
            select(func.count())
            .select_from(OrganizationMember)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == organization.id, User.is_active.is_(True))
        ),
    }


def profile_organizations(db, user, viewer):
    organizations = db.scalars(
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == user.id, visible_to(viewer))
        .order_by(Organization.name, Organization.id)
    )
    return [organization_data(db, item, viewer) for item in organizations]


def save(db):
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "An organization with this URL name already exists") from error


@router.get("")
def list_organizations(
    q: str = Query(default="", max_length=100),
    scope: Literal["public", "mine"] = "public",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(optional_user),
):
    filters = [visible_to(user)]
    if scope == "mine":
        if user is None:
            raise HTTPException(401, "Sign in to view your organizations")
        filters.append(
            exists().where(
                OrganizationMember.organization_id == Organization.id,
                OrganizationMember.user_id == user.id,
            )
        )
    else:
        filters.append(Organization.visibility == "public")
    if q.strip():
        term = q.strip()
        filters.append(
            or_(
                Organization.name.icontains(term, autoescape=True),
                Organization.slug.icontains(term, autoescape=True),
                Organization.description.icontains(term, autoescape=True),
            )
        )
    organizations = db.scalars(
        select(Organization)
        .where(*filters)
        .order_by(Organization.name, Organization.id)
        .offset(offset)
        .limit(limit)
    )
    return {
        "items": [organization_data(db, item, user) for item in organizations],
        "total": db.scalar(select(func.count()).select_from(Organization).where(*filters)),
    }


@router.post("", status_code=201)
def create_organization(
    payload: OrganizationCreate, db=Depends(get_db), user=Depends(current_user)
):
    fields = payload.model_dump()
    fields["social_links"] = json.dumps(fields["social_links"])
    organization = Organization(**fields)
    db.add(organization)
    try:
        db.flush()
        db.add(OrganizationMember(organization_id=organization.id, user_id=user.id, role="owner"))
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "An organization with this URL name already exists") from error
    return organization_data(db, organization, user)


@router.get("/{slug}")
def get_organization(slug: str, db=Depends(get_db), user=Depends(optional_user)):
    organization, _ = access(db, slug, user)
    return {
        **organization_data(db, organization, user),
        "contact_email": organization.contact_email,
        "social_links": json.loads(organization.social_links),
    }


@router.put("/{slug}")
def update_organization(
    slug: str, payload: OrganizationUpdate, db=Depends(get_db), user=Depends(current_user)
):
    with mutation_lock:
        organization, role = access(db, slug, user, edit=True, lock=True)
        if payload.visibility != organization.visibility and role != "owner":
            raise HTTPException(403, "Only Owners can change organization visibility")
        for key, value in payload.model_dump().items():
            setattr(organization, key, json.dumps(value) if key == "social_links" else value)
        save(db)
        return get_organization(slug, db, user)


@router.delete("/{slug}", status_code=204)
def delete_organization(slug: str, db=Depends(get_db), user=Depends(current_user)):
    with mutation_lock:
        organization, role = access(db, slug, user, edit=True, lock=True)
        if role != "owner":
            raise HTTPException(403, "Only Owners can delete organizations")
        if db.scalar(
            select(Repository.id).where(Repository.organization_id == organization.id).limit(1)
        ):
            raise HTTPException(409, "Organizations containing repositories cannot be deleted")
        db.execute(
            delete(OrganizationMember).where(OrganizationMember.organization_id == organization.id)
        )
        db.delete(organization)
        db.commit()
    return Response(status_code=204)


@router.get("/{slug}/repositories")
def list_repositories(
    slug: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(optional_user),
):
    organization, _ = access(db, slug, user)
    filters = (Repository.organization_id == organization.id, repositories_visible(user))
    items = db.scalars(
        select(Repository)
        .where(*filters)
        .order_by(Repository.created_at.desc(), Repository.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return {
        "items": [repo_data(db, item, user) for item in items],
        "total": db.scalar(select(func.count()).select_from(Repository).where(*filters)),
    }


@router.get("/{slug}/members")
def list_members(slug: str, db=Depends(get_db), user=Depends(optional_user)):
    organization, _ = access(db, slug, user)
    members = db.execute(
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == organization.id, User.is_active.is_(True))
        .order_by(User.username)
    )
    return [
        {
            "username": account.username,
            "display_name": account.display_name,
            "avatar_url": avatar_url(account),
            "role": membership.role,
            "joined_at": attribute(membership, "created_at"),
        }
        for membership, account in members
    ]


def protect_last_owner(db, organization, membership):
    if membership.role != "owner":
        return
    owners = db.scalars(
        select(OrganizationMember.id)
        .join(User, User.id == OrganizationMember.user_id)
        .where(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.role == "owner",
            User.is_active.is_(True),
            User.id != membership.user_id,
        )
        .with_for_update(of=OrganizationMember)
    ).all()
    if not owners:
        raise HTTPException(409, "Assign another Owner before removing or demoting the last Owner")


@router.put("/{slug}/members")
def set_member(
    slug: str, payload: OrganizationMemberInput, db=Depends(get_db), user=Depends(current_user)
):
    with mutation_lock:
        organization, role = access(db, slug, user, edit=True, lock=True)
        target = db.scalar(
            select(User).where(User.username == payload.username.lower(), User.is_active.is_(True))
        )
        if target is None:
            raise HTTPException(404, "User not found")
        membership = db.scalar(
            select(OrganizationMember)
            .where(
                OrganizationMember.organization_id == organization.id,
                OrganizationMember.user_id == target.id,
            )
            .with_for_update()
        )
        if role != "owner" and (
            payload.role != "reader" or (membership and membership.role != "reader")
        ):
            raise HTTPException(403, "Maintainers can only add or manage Readers")
        if membership:
            if membership.role != payload.role:
                protect_last_owner(db, organization, membership)
            membership.role = payload.role
        else:
            db.add(
                OrganizationMember(
                    organization_id=organization.id, user_id=target.id, role=payload.role
                )
            )
        save(db)
    return {"status": "ok"}


@router.delete("/{slug}/members/{username}", status_code=204)
def remove_member(slug: str, username: str, db=Depends(get_db), user=Depends(current_user)):
    with mutation_lock:
        organization, role = access(db, slug, user, lock=True)
        membership = db.scalar(
            select(OrganizationMember)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.organization_id == organization.id,
                User.username == username.lower(),
            )
            .with_for_update(of=OrganizationMember)
        )
        if membership is None:
            raise HTTPException(404, "Member not found")
        if (
            membership.user_id != user.id
            and role != "owner"
            and not (role == "maintainer" and membership.role == "reader")
        ):
            raise HTTPException(403, "You cannot remove this member")
        protect_last_owner(db, organization, membership)
        db.delete(membership)
        db.commit()
    return Response(status_code=204)


@router.put("/{slug}/avatar")
async def upload_avatar(
    slug: str, request: Request, db=Depends(get_db), user=Depends(current_user)
):
    access(db, slug, user, edit=True)
    throttle(f"organization-avatar:{user.id}")
    normalized = await read_avatar(request)
    with mutation_lock:
        organization, _ = access(db, slug, user, edit=True, lock=True)
        organization.avatar = normalized
        organization.avatar_digest = hashlib.sha256(normalized).hexdigest()
        db.commit()
        return {"avatar_url": organization_data(db, organization, user)["avatar_url"]}


@router.delete("/{slug}/avatar")
def remove_avatar(slug: str, db=Depends(get_db), user=Depends(current_user)):
    with mutation_lock:
        organization, _ = access(db, slug, user, edit=True, lock=True)
        organization.avatar = None
        organization.avatar_digest = None
        db.commit()
    return {"avatar_url": None}


@router.get("/{slug}/avatar/{digest}.png")
def avatar(slug: str, digest: str, db=Depends(get_db), user=Depends(optional_user)):
    organization, _ = access(db, slug, user)
    if organization.avatar_digest != digest or organization.avatar is None:
        raise HTTPException(404, "Profile picture not found")
    return Response(content=organization.avatar, media_type="image/png")
