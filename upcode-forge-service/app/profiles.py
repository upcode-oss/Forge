import json
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, or_, select

from app import git_service as git
from app.api import attribute, repo_data
from app.avatars import avatar_url
from app.database import get_db
from app.models import Comment, Membership, Repository, Ticket, User
from app.organizations import profile_organizations
from app.schemas import ProfileUpdate
from app.security import current_user, optional_user

router = APIRouter(prefix="/api/v1")


def profile_data(user):
    return {
        **{
            key: attribute(user, key)
            for key in (
                "username",
                "display_name",
                "bio",
                "company",
                "location",
                "website",
                "public_email",
                "created_at",
            )
        },
        "social_links": json.loads(user.social_links),
        "avatar_url": avatar_url(user),
    }


@router.get("/profile")
def own_profile(user=Depends(current_user)):
    return profile_data(user)


@router.put("/profile")
def update_profile(payload: ProfileUpdate, db=Depends(get_db), user=Depends(current_user)):
    for key, value in payload.model_dump().items():
        if key == "social_links":
            value = json.dumps(value)
        elif key == "public_email" and value:
            value = str(value).lower()
        setattr(user, key, value)
    db.commit()
    return profile_data(user)


def contributions(db, user, year):
    today = datetime.now(UTC).date()
    start = date(year, 1, 1)
    end = min(date(year, 12, 31), today)
    begin = datetime.combine(start, time.min, UTC)
    finish = datetime.combine(end + timedelta(days=1), time.min, UTC)
    days = {
        (start + timedelta(days=offset)).isoformat(): {"count": 0, "private_count": 0}
        for offset in range((end - start).days + 1)
    }
    totals = {kind: 0 for kind in ("commits", "repositories", "issues", "pulls", "comments")}

    def add(kind, occurred, visibility):
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=UTC)
        day = occurred.astimezone(UTC).date().isoformat()
        if day in days:
            days[day]["count"] += 1
            if visibility == "private":
                days[day]["private_count"] += 1
            else:
                totals[kind] += 1

    public = Repository.visibility == "public"
    eligible = or_(
        public,
        Repository.owner_id == user.id,
        exists().where(Membership.repository_id == Repository.id, Membership.user_id == user.id),
    )
    for occurred, visibility in db.execute(
        select(Repository.created_at, Repository.visibility).where(
            Repository.owner_id == user.id,
            Repository.created_at >= begin,
            Repository.created_at < finish,
        )
    ):
        add("repositories", occurred, visibility)
    for kind, occurred, visibility in db.execute(
        select(Ticket.kind, Ticket.created_at, Repository.visibility)
        .select_from(Ticket)
        .join(Repository, Repository.id == Ticket.repository_id)
        .where(
            eligible,
            Ticket.author_id == user.id,
            Ticket.created_at >= begin,
            Ticket.created_at < finish,
        )
    ):
        add("pulls" if kind == "pull" else "issues", occurred, visibility)
    for occurred, visibility in db.execute(
        select(Comment.created_at, Repository.visibility)
        .select_from(Comment)
        .join(Ticket, Ticket.id == Comment.ticket_id)
        .join(Repository, Repository.id == Ticket.repository_id)
        .where(
            eligible,
            Comment.author_id == user.id,
            Comment.created_at >= begin,
            Comment.created_at < finish,
        )
    ):
        add("comments", occurred, visibility)

    seen = set()
    incomplete = False
    # Read actual Git history so imported commits and HTTP pushes appear immediately.
    # Public copies take precedence when a commit exists in both public and private repositories.
    for repository in db.scalars(
        select(Repository).where(eligible).order_by(public.desc(), Repository.id)
    ):
        try:
            output = git.run(
                git.path_for(repository),
                "log",
                "--all",
                f"--since-as-filter={begin.isoformat()}",
                f"--until={finish.isoformat()}",
                "--regexp-ignore-case",
                "--fixed-strings",
                f"--author=<{user.email}>",
                "--format=%H%x00%ae%x00%ct",
                "--",
            )
            for row in output.decode("utf-8", "replace").splitlines():
                sha, email, timestamp = row.split("\0")
                if sha not in seen and email.casefold() == user.email.casefold():
                    add(
                        "commits",
                        datetime.fromtimestamp(int(timestamp), UTC),
                        repository.visibility,
                    )
                    seen.add(sha)
        except (HTTPException, OSError, ValueError, OverflowError):
            incomplete = True
    longest = streak = 0
    for counts in days.values():
        streak = streak + 1 if counts["count"] else 0
        longest = max(longest, streak)
    return {
        "year": year,
        "days": [{"date": day, **counts} for day, counts in days.items()],
        "totals": totals,
        "total": sum(counts["count"] for counts in days.values()),
        "private_total": sum(counts["private_count"] for counts in days.values()),
        "longest_streak": longest,
        "incomplete": incomplete,
    }


@router.get("/profiles/{username}")
def public_profile(
    username: str,
    year: int | None = Query(default=None, ge=1970, le=9999),
    db=Depends(get_db),
    viewer=Depends(optional_user),
):
    user = db.scalar(
        select(User).where(User.username == username.lower(), User.is_active.is_(True))
    )
    if user is None:
        raise HTTPException(404, "Profile not found")
    this_year = datetime.now(UTC).year
    registration_year = attribute(user, "created_at").astimezone(UTC).year
    year = year or this_year
    if not registration_year <= year <= this_year:
        raise HTTPException(422, f"Choose a year between {registration_year} and {this_year}")
    owned = (Repository.owner_id == user.id, Repository.visibility == "public")
    repositories = db.scalars(
        select(Repository).where(*owned).order_by(Repository.created_at.desc()).limit(100)
    )
    return {
        **profile_data(user),
        "organizations": profile_organizations(db, user, viewer),
        "repository_count": db.scalar(select(func.count()).select_from(Repository).where(*owned)),
        "repositories": [repo_data(db, item, None) for item in repositories],
        "activity": {
            **contributions(db, user, year),
            "available_years": list(range(registration_year, this_year + 1)),
        },
    }
