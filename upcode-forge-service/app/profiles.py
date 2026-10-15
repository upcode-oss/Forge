import json
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app import git_service as git
from app.api import attribute, repo_data
from app.database import get_db
from app.models import Comment, Repository, Ticket, User
from app.schemas import ProfileUpdate
from app.security import current_user

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
        (start + timedelta(days=offset)).isoformat(): 0 for offset in range((end - start).days + 1)
    }
    totals = {kind: 0 for kind in ("commits", "repositories", "issues", "pulls", "comments")}

    def add(kind, occurred):
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=UTC)
        day = occurred.astimezone(UTC).date().isoformat()
        if day in days:
            days[day] += 1
            totals[kind] += 1

    public = Repository.visibility == "public"
    for occurred in db.scalars(
        select(Repository.created_at).where(
            public,
            Repository.owner_id == user.id,
            Repository.created_at >= begin,
            Repository.created_at < finish,
        )
    ):
        add("repositories", occurred)
    for kind, occurred in db.execute(
        select(Ticket.kind, Ticket.created_at)
        .join(Repository)
        .where(
            public,
            Ticket.author_id == user.id,
            Ticket.created_at >= begin,
            Ticket.created_at < finish,
        )
    ):
        add("pulls" if kind == "pull" else "issues", occurred)
    for occurred in db.scalars(
        select(Comment.created_at)
        .join(Ticket)
        .join(Repository)
        .where(
            public,
            Comment.author_id == user.id,
            Comment.created_at >= begin,
            Comment.created_at < finish,
        )
    ):
        add("comments", occurred)

    seen = set()
    incomplete = False
    # Read actual Git history so imported commits and HTTP pushes appear immediately.
    # Only public repositories participate, even when the profile owner is signed in.
    for repository in db.scalars(select(Repository).where(public)):
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
                    add("commits", datetime.fromtimestamp(int(timestamp), UTC))
                    seen.add(sha)
        except (HTTPException, OSError, ValueError, OverflowError):
            incomplete = True
    longest = streak = 0
    for count in days.values():
        streak = streak + 1 if count else 0
        longest = max(longest, streak)
    return {
        "year": year,
        "days": [{"date": day, "count": count} for day, count in days.items()],
        "totals": totals,
        "total": sum(totals.values()),
        "longest_streak": longest,
        "incomplete": incomplete,
    }


@router.get("/profiles/{username}")
def public_profile(
    username: str,
    year: int | None = Query(default=None, ge=1970, le=9999),
    db=Depends(get_db),
):
    user = db.scalar(
        select(User).where(User.username == username.lower(), User.is_active.is_(True))
    )
    if user is None:
        raise HTTPException(404, "Profile not found")
    this_year = datetime.now(UTC).year
    year = year or this_year
    if year > this_year:
        raise HTTPException(422, "Choose the current year or an earlier year")
    owned = (Repository.owner_id == user.id, Repository.visibility == "public")
    repositories = db.scalars(
        select(Repository).where(*owned).order_by(Repository.created_at.desc()).limit(100)
    )
    return {
        **profile_data(user),
        "repository_count": db.scalar(select(func.count()).select_from(Repository).where(*owned)),
        "repositories": [repo_data(db, item, None) for item in repositories],
        "activity": contributions(db, user, year),
    }
