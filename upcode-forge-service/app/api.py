import json
import secrets
import shutil
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import URL, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import database, organization_access, repository_import
from app import git_service as git
from app.avatars import avatar_url
from app.config import settings
from app.database import get_db
from app.models import (
    AccessToken,
    Comment,
    Instance,
    Membership,
    Organization,
    OrganizationMember,
    Repository,
    Ticket,
    User,
)
from app.repository_access import access, role, visible
from app.schemas import (
    SMTP,
    CommentInput,
    Credentials,
    InstanceUpdate,
    MemberInput,
    PasswordInput,
    RepoCreate,
    RepoImport,
    RepoUpdate,
    Setup,
    TicketCreate,
    TokenInput,
    UserCreate,
)
from app.security import (
    admin_user,
    current_user,
    digest,
    dummy_hash,
    hasher,
    issue_token,
    throttle,
    verify,
)
from app.ssh_support import ssh_clone_url

router = APIRouter(prefix="/api/v1")


def attribute(item, key):
    value = getattr(item, key)
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def user_data(user):
    data = {
        key: attribute(user, key)
        for key in (
            "id",
            "username",
            "email",
            "display_name",
            "is_admin",
            "is_active",
            "created_at",
        )
    }
    return {**data, "avatar_url": avatar_url(user)}


def repo_data(db, repo, user):
    organization = db.get(Organization, repo.organization_id) if repo.organization_id else None
    owner = organization.slug if organization else db.get(User, repo.owner_id).username
    namespace = f"organizations/{owner}" if organization else owner
    instance = db.get(Instance, 1)
    return {
        **{
            key: attribute(repo, key)
            for key in ("id", "name", "description", "visibility", "default_branch", "created_at")
        },
        "owner": owner,
        "owner_type": "organization" if organization else "user",
        "owner_profile_url": f"/o/{owner}" if organization else f"/u/{owner}",
        "organization_visibility": organization.visibility if organization else None,
        "visibility": "private"
        if organization and organization.visibility == "private"
        else repo.visibility,
        "role": role(db, repo, user),
        "clone_url": f"{instance.public_url}/git/{namespace}/{repo.name}.git",
        "ssh_clone_url": ssh_clone_url(instance.public_url, namespace, repo.name),
    }


def commit(db):
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "This name or email is already in use") from error


@router.get("/setup/status")
def setup_status():
    return {"completed": database.engine is not None}


@router.post("/setup", status_code=201)
def setup(payload: Setup, request: Request):
    throttle(f"setup:{request.client.host}")
    if not secrets.compare_digest(payload.setup_token, settings().setup_token):
        raise HTTPException(403, "Invalid setup token. Use FORGE_SETUP_TOKEN from your .env file.")
    git.valid_branch(payload.default_branch)
    with database.setup_lock():
        if database.engine is not None or (settings().data_dir / "installation.json").exists():
            raise HTTPException(409, "Setup is already complete")
        if payload.database_engine == "sqlite":
            url = f"sqlite:///{settings().data_dir / 'forge.db'}"
        else:
            url = URL.create(
                "postgresql+psycopg"
                if payload.database_engine == "postgresql"
                else "mysql+pymysql",
                username=payload.database_user,
                password=payload.database_password,
                host=payload.database_host,
                port=payload.database_port,
                database=payload.database_name,
            ).render_as_string(hide_password=False)
        target = database.make_engine(url)
        try:
            database.migrate(target)
            with Session(target) as db:
                if db.get(Instance, 1):
                    raise HTTPException(
                        409,
                        "Database already contains an installation. Restore installation.json from backup.",
                    )
                instance = Instance(
                    id=1,
                    name=payload.name,
                    public_url=payload.public_url,
                    default_branch=payload.default_branch,
                )
                if payload.smtp and payload.smtp.host:
                    instance.smtp_config = (
                        database.cipher().encrypt(payload.smtp.model_dump_json().encode()).decode()
                    )
                db.add(instance)
                admin = payload.admin
                db.add(
                    User(
                        username=admin.username,
                        email=str(admin.email).lower(),
                        display_name=admin.display_name,
                        password_hash=hasher.hash(admin.password),
                        is_admin=True,
                    )
                )
                db.commit()
            database.save(url)
        except HTTPException:
            target.dispose()
            raise
        except Exception as error:
            target.dispose()
            raise HTTPException(
                400, "Setup failed. Check the database connection and writable storage."
            ) from error
        database.engine = target
    return {"completed": True}


@router.post("/auth/login")
def login(payload: Credentials, request: Request, response: Response, db=Depends(get_db)):
    throttle(f"login:{request.client.host}")
    user = db.scalar(select(User).where(User.username == payload.username.lower()))
    valid = verify(payload.password, user.password_hash if user else dummy_hash)
    if not user or not valid or not user.is_active:
        raise HTTPException(401, "Invalid username or password")
    raw = issue_token(db, user, "Browser session")
    response.set_cookie(
        "forge_session",
        raw,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="lax",
        max_age=int(timedelta(days=7).total_seconds()),
        path="/",
    )
    return user_data(user)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db=Depends(get_db)):
    db.execute(
        delete(AccessToken).where(
            AccessToken.digest == digest(request.cookies.get("forge_session", "")),
            AccessToken.kind == "session",
        )
    )
    db.commit()
    response.delete_cookie("forge_session", path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user=Depends(current_user)):
    return user_data(user)


@router.post("/auth/password")
def password(
    payload: PasswordInput, request: Request, db=Depends(get_db), user=Depends(current_user)
):
    throttle(f"password:{user.id}")
    if not verify(payload.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hasher.hash(payload.new_password)
    db.execute(delete(AccessToken).where(AccessToken.user_id == user.id))
    db.commit()
    return {"ok": True}


@router.get("/instance")
def instance(db=Depends(get_db), user=Depends(current_user)):
    item = db.get(Instance, 1)
    return {
        "name": item.name,
        "public_url": item.public_url,
        "default_branch": item.default_branch,
        "version": "0.1.0",
    }


@router.put("/instance")
def update_instance(payload: InstanceUpdate, db=Depends(get_db), user=Depends(admin_user)):
    git.valid_branch(payload.default_branch)
    item = db.get(Instance, 1)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return {"ok": True}


@router.get("/instance/smtp")
def smtp_get(db=Depends(get_db), user=Depends(admin_user)):
    value = db.get(Instance, 1).smtp_config
    data = json.loads(database.cipher().decrypt(value.encode())) if value else SMTP().model_dump()
    data["password"] = ""
    return {
        **data,
        "has_password": bool(
            value and json.loads(database.cipher().decrypt(value.encode())).get("password")
        ),
    }


@router.put("/instance/smtp")
def smtp_save(payload: SMTP, db=Depends(get_db), user=Depends(admin_user)):
    item = db.get(Instance, 1)
    if not payload.password and item.smtp_config:
        payload.password = json.loads(database.cipher().decrypt(item.smtp_config.encode())).get(
            "password", ""
        )
    item.smtp_config = (
        database.cipher().encrypt(payload.model_dump_json().encode()).decode()
        if payload.host
        else None
    )
    db.commit()
    return {"ok": True}


@router.post("/instance/smtp/test")
def smtp_test(db=Depends(get_db), user=Depends(admin_user)):
    import smtplib
    import ssl
    from email.message import EmailMessage

    value = db.get(Instance, 1).smtp_config
    if not value:
        raise HTTPException(400, "Save the SMTP configuration first")
    config = SMTP.model_validate_json(database.cipher().decrypt(value.encode()))
    if not config.from_address:
        raise HTTPException(400, "Set a sender email first")
    message = EmailMessage()
    message["Subject"] = "Upcode Forge SMTP test"
    message["From"], message["To"] = str(config.from_address), user.email
    message.set_content("Your Upcode Forge email configuration works.")
    try:
        client = smtplib.SMTP_SSL if config.encryption == "tls" else smtplib.SMTP
        options = {"context": ssl.create_default_context()} if config.encryption == "tls" else {}
        with client(config.host, config.port, timeout=10, **options) as connection:
            if config.encryption == "starttls":
                connection.starttls(context=ssl.create_default_context())
            if config.username:
                connection.login(config.username, config.password)
            connection.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise HTTPException(400, "SMTP test failed. Check the server and credentials.") from error
    return {"ok": True}


@router.get("/users")
def users(db=Depends(get_db), user=Depends(admin_user)):
    return [user_data(item) for item in db.scalars(select(User).order_by(User.username).limit(500))]


@router.post("/users", status_code=201)
def create_user(payload: UserCreate, db=Depends(get_db), user=Depends(admin_user)):
    item = User(
        username=payload.username,
        email=str(payload.email).lower(),
        display_name=payload.display_name,
        password_hash=hasher.hash(payload.password),
        is_admin=payload.is_admin,
    )
    db.add(item)
    commit(db)
    return user_data(item)


@router.put("/users/{user_id}/active")
def active_user(user_id: int, active: bool, db=Depends(get_db), user=Depends(admin_user)):
    item = db.get(User, user_id)
    if not item:
        raise HTTPException(404, "User not found")
    if item.id == user.id:
        raise HTTPException(400, "You cannot deactivate your own account")
    item.is_active = active
    if not active:
        db.execute(delete(AccessToken).where(AccessToken.user_id == user_id))
    db.commit()
    return user_data(item)


@router.get("/tokens")
def tokens(db=Depends(get_db), user=Depends(current_user)):
    return [
        {key: attribute(item, key) for key in ("id", "name", "scope", "expires_at", "created_at")}
        for item in db.scalars(
            select(AccessToken).where(AccessToken.user_id == user.id, AccessToken.kind == "git")
        )
    ]


@router.post("/tokens", status_code=201)
def create_token(payload: TokenInput, db=Depends(get_db), user=Depends(current_user)):
    return {"token": issue_token(db, user, payload.name, "git", payload.scope, payload.days)}


@router.delete("/tokens/{token_id}")
def revoke(token_id: int, db=Depends(get_db), user=Depends(current_user)):
    db.execute(
        delete(AccessToken).where(
            AccessToken.id == token_id, AccessToken.user_id == user.id, AccessToken.kind == "git"
        )
    )
    db.commit()
    return {"ok": True}


@router.get("/repositories")
def repositories(db=Depends(get_db), user=Depends(current_user)):
    return [
        repo_data(db, item, user)
        for item in db.scalars(
            select(Repository)
            .where(visible(user))
            .order_by(Repository.created_at.desc())
            .limit(500)
        )
    ]


@router.get("/dashboard")
def dashboard(db=Depends(get_db), user=Depends(current_user)):
    ids = select(Repository.id).where(visible(user))
    return {
        "repositories": db.scalar(
            select(func.count()).select_from(Repository).where(visible(user))
        ),
        "issues": db.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.repository_id.in_(ids), Ticket.kind == "issue", Ticket.state == "open")
        ),
        "pulls": db.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.repository_id.in_(ids), Ticket.kind == "pull", Ticket.state == "open")
        ),
    }


@router.get("/repository-owners")
def repository_owners(db=Depends(get_db), user=Depends(current_user)):
    organizations = db.scalars(
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(
            OrganizationMember.user_id == user.id,
            OrganizationMember.role.in_(("owner", "maintainer")),
        )
        .order_by(Organization.name, Organization.id)
    )
    return {
        "username": user.username,
        "organizations": [
            {"slug": item.slug, "name": item.name, "visibility": item.visibility}
            for item in organizations
        ],
    }


def store_repository(payload, db, user, *, importing=False):
    with organization_access.mutation_lock if payload.organization else nullcontext():
        organization = None
        if payload.organization:
            organization, _ = organization_access.access(
                db, payload.organization, user, edit=True, lock=True
            )
            if organization.visibility == "private" and payload.visibility == "public":
                raise HTTPException(422, "Repositories in private organizations must be private")
        item = Repository(
            owner_id=None if organization else user.id,
            organization_id=organization.id if organization else None,
            created_by_id=user.id,
            name=payload.name,
            description=payload.description,
            visibility=payload.visibility,
            default_branch=db.get(Instance, 1).default_branch,
        )
        db.add(item)
        try:
            db.flush()
        except IntegrityError as error:
            db.rollback()
            raise HTTPException(
                409, "A repository with this name already exists for this owner"
            ) from error
        try:
            if importing:
                repository_import.clone(item, payload)
            else:
                git.initialize(item, user, payload.initialize)
            db.commit()
        except Exception:
            shutil.rmtree(git.path_for(item), ignore_errors=True)
            db.rollback()
            raise
        return repo_data(db, item, user)


@router.post("/repositories", status_code=201)
def create_repository(payload: RepoCreate, db=Depends(get_db), user=Depends(current_user)):
    return store_repository(payload, db, user)


@router.post("/repositories/import", status_code=201)
def import_repository(payload: RepoImport, db=Depends(get_db), user=Depends(current_user)):
    throttle(f"import:{user.id}")
    return store_repository(payload, db, user, importing=True)


@router.get("/repositories/{repo_id}")
def repository(repo_id: int, db=Depends(get_db), user=Depends(current_user)):
    return repo_data(db, access(db, repo_id, user), user)


@router.put("/repositories/{repo_id}")
def update_repository(
    repo_id: int, payload: RepoUpdate, db=Depends(get_db), user=Depends(current_user)
):
    item = access(db, repo_id, user, "maintain")
    if item.organization_id and payload.visibility == "public":
        organization = db.get(Organization, item.organization_id)
        if organization.visibility == "private":
            raise HTTPException(422, "Repositories in private organizations must be private")
    git.valid_branch(payload.default_branch)
    if payload.default_branch not in git.branches(item):
        raise HTTPException(400, "Push this branch before making it the default")
    git.run(git.path_for(item), "symbolic-ref", "HEAD", f"refs/heads/{payload.default_branch}")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return repo_data(db, item, user)


@router.get("/repositories/{repo_id}/branches")
def list_branches(repo_id: int, db=Depends(get_db), user=Depends(current_user)):
    return git.branches(access(db, repo_id, user))


@router.get("/repositories/{repo_id}/tree")
def tree(repo_id: int, ref: str, path: str = "", db=Depends(get_db), user=Depends(current_user)):
    return git.tree(access(db, repo_id, user), ref, path)


@router.get("/repositories/{repo_id}/blob")
def blob(repo_id: int, ref: str, path: str, db=Depends(get_db), user=Depends(current_user)):
    return git.blob(access(db, repo_id, user), ref, path)


@router.get("/repositories/{repo_id}/commits")
def commits(
    repo_id: int, ref: str, offset: int = 0, db=Depends(get_db), user=Depends(current_user)
):
    if offset < 0 or offset > 100000:
        raise HTTPException(422, "Invalid offset")
    return git.commits(access(db, repo_id, user), ref, offset)


@router.get("/repositories/{repo_id}/commits/{sha}")
def commit_diff(repo_id: int, sha: str, db=Depends(get_db), user=Depends(current_user)):
    item = access(db, repo_id, user)
    oid = git.resolve(git.path_for(item), sha)
    return {
        "diff": git.run(
            git.path_for(item),
            "show",
            "--format=fuller",
            "--no-ext-diff",
            "--no-textconv",
            oid,
            "--",
        ).decode("utf-8", "replace")
    }


@router.get("/repositories/{repo_id}/members")
def members(repo_id: int, db=Depends(get_db), user=Depends(current_user)):
    access(db, repo_id, user, "maintain")
    return [
        {"id": item.id, "username": db.get(User, item.user_id).username, "role": item.role}
        for item in db.scalars(select(Membership).where(Membership.repository_id == repo_id))
    ]


@router.put("/repositories/{repo_id}/members")
def add_member(repo_id: int, payload: MemberInput, db=Depends(get_db), user=Depends(current_user)):
    item = access(db, repo_id, user, "maintain")
    target = db.scalar(
        select(User).where(User.username == payload.username, User.is_active.is_(True))
    )
    if not target or target.id == item.owner_id:
        raise HTTPException(400, "Select an active user other than the repository owner")
    member = db.scalar(
        select(Membership).where(
            Membership.repository_id == repo_id, Membership.user_id == target.id
        )
    )
    if not member:
        member = Membership(repository_id=repo_id, user_id=target.id)
        db.add(member)
    member.role = payload.role
    commit(db)
    return {"ok": True}


@router.delete("/repositories/{repo_id}/members/{member_id}")
def remove_member(repo_id: int, member_id: int, db=Depends(get_db), user=Depends(current_user)):
    access(db, repo_id, user, "maintain")
    db.execute(
        delete(Membership).where(Membership.id == member_id, Membership.repository_id == repo_id)
    )
    db.commit()
    return {"ok": True}


def ticket_data(db, item):
    return {
        **{
            key: attribute(item, key)
            for key in (
                "id",
                "kind",
                "title",
                "body",
                "state",
                "source_branch",
                "target_branch",
                "created_at",
            )
        },
        "author": db.get(User, item.author_id).username,
    }


def get_ticket(db, repo_id, ticket_id, user, level="read"):
    access(db, repo_id, user, level)
    item = db.get(Ticket, ticket_id)
    if not item or item.repository_id != repo_id:
        raise HTTPException(404, "Issue or pull request not found")
    return item


@router.get("/repositories/{repo_id}/tickets")
def tickets(repo_id: int, kind: str = "issue", db=Depends(get_db), user=Depends(current_user)):
    access(db, repo_id, user)
    return [
        ticket_data(db, item)
        for item in db.scalars(
            select(Ticket)
            .where(Ticket.repository_id == repo_id, Ticket.kind == kind)
            .order_by(Ticket.id.desc())
            .limit(500)
        )
    ]


@router.post("/repositories/{repo_id}/tickets", status_code=201)
def create_ticket(
    repo_id: int, payload: TicketCreate, db=Depends(get_db), user=Depends(current_user)
):
    repo = access(db, repo_id, user, "write")
    if payload.kind == "pull":
        if (
            not payload.source_branch
            or not payload.target_branch
            or payload.source_branch == payload.target_branch
        ):
            raise HTTPException(422, "Select two different branches")
        git.compare(repo, payload.source_branch, payload.target_branch)
    item = Ticket(repository_id=repo_id, author_id=user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    return ticket_data(db, item)


@router.get("/repositories/{repo_id}/tickets/{ticket_id}")
def ticket(repo_id: int, ticket_id: int, db=Depends(get_db), user=Depends(current_user)):
    item = get_ticket(db, repo_id, ticket_id, user)
    comments = [
        {
            "id": c.id,
            "body": c.body,
            "author": db.get(User, c.author_id).username,
            "created_at": attribute(c, "created_at"),
        }
        for c in db.scalars(
            select(Comment).where(Comment.ticket_id == item.id).order_by(Comment.id)
        )
    ]
    return {**ticket_data(db, item), "comments": comments}


@router.post("/repositories/{repo_id}/tickets/{ticket_id}/comments", status_code=201)
def comment(
    repo_id: int,
    ticket_id: int,
    payload: CommentInput,
    db=Depends(get_db),
    user=Depends(current_user),
):
    get_ticket(db, repo_id, ticket_id, user, "write")
    db.add(Comment(ticket_id=ticket_id, author_id=user.id, body=payload.body))
    db.commit()
    return {"ok": True}


@router.put("/repositories/{repo_id}/tickets/{ticket_id}/state")
def ticket_state(
    repo_id: int, ticket_id: int, state: str, db=Depends(get_db), user=Depends(current_user)
):
    item = get_ticket(db, repo_id, ticket_id, user, "write")
    if state not in ("open", "closed") or item.state == "merged":
        raise HTTPException(400, "Invalid state transition")
    item.state = state
    db.commit()
    return ticket_data(db, item)


@router.get("/repositories/{repo_id}/tickets/{ticket_id}/diff")
def pull_diff(repo_id: int, ticket_id: int, db=Depends(get_db), user=Depends(current_user)):
    item = get_ticket(db, repo_id, ticket_id, user)
    if item.kind != "pull":
        raise HTTPException(400, "This is not a pull request")
    return {"diff": git.compare(access(db, repo_id, user), item.source_branch, item.target_branch)}


@router.post("/repositories/{repo_id}/tickets/{ticket_id}/merge")
def merge_pull(repo_id: int, ticket_id: int, db=Depends(get_db), user=Depends(current_user)):
    item = get_ticket(db, repo_id, ticket_id, user, "maintain")
    if item.kind != "pull" or item.state != "open":
        raise HTTPException(400, "Only open pull requests can be merged")
    sha = git.merge(access(db, repo_id, user, "maintain"), item, user)
    item.state = "merged"
    db.commit()
    return {"sha": sha}
