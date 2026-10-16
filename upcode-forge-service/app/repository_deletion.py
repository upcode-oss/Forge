import logging
import secrets
import shutil

from sqlalchemy import delete, select

from app import git_service as git
from app.models import Comment, Membership, Ticket

logger = logging.getLogger(__name__)


def remove(db, repository):
    path = git.path_for(repository)
    retired = path.with_name(f".deleting-{repository.id}-{secrets.token_hex(12)}.git")
    moved = False
    try:
        path.rename(retired)
        moved = True
    except FileNotFoundError:
        # Allow removal of database entries whose Git directory is already missing.
        pass

    try:
        tickets = select(Ticket.id).where(Ticket.repository_id == repository.id)
        db.execute(delete(Comment).where(Comment.ticket_id.in_(tickets)))
        db.execute(delete(Ticket).where(Ticket.repository_id == repository.id))
        db.execute(delete(Membership).where(Membership.repository_id == repository.id))
        db.delete(repository)
        db.commit()
    except Exception:
        db.rollback()
        if moved:
            retired.rename(path)
        raise

    if moved:
        try:
            shutil.rmtree(retired)
        except OSError:
            # SQL deletion has committed. Keep failed cleanup isolated from new
            # repositories, even when SQLite reuses the deleted repository ID.
            logger.exception("Could not remove deleted repository files at %s", retired)
