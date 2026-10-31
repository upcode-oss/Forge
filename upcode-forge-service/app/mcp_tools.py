from typing import Annotated, Literal

from pydantic import Field

from app.mcp_toolkit import APITool
from app.schemas import CommentInput, MemberInput, RepoCreate, RepoUpdate, TicketCreate

ID = Annotated[int, Field(gt=0)]
REPO = {"repo_id": ID}
TICKET = {**REPO, "ticket_id": ID}
TEXT = (str | None, Field(default=None, max_length=200))
REF = (str, Field(min_length=1, max_length=500))

SCOPE_DESCRIPTIONS = {
    "profile.read": "Read your own account profile",
    "repositories.read": "Read accessible repositories, code, issues, and pull requests",
    "repositories.write": "Create issues and pull requests, comment, and change ticket state",
    "repositories.maintain": "Manage repositories and collaborators, delete repositories, and merge pull requests",
    "repositories.create": "Create repositories you are allowed to own",
}

TOOLS = [
    APITool(
        "get_current_user",
        "Read the authenticated key owner's profile.",
        "profile.read",
        "GET",
        "/auth/me",
    ),
    APITool(
        "list_repositories",
        "List only repositories visible to the key owner.",
        "repositories.read",
        "GET",
        "/repositories",
        query_fields={"scope": (Literal["accessible", "public"], "accessible")},
    ),
    APITool(
        "get_repository",
        "Read an accessible repository's metadata.",
        "repositories.read",
        "GET",
        "/repositories/{repo_id}",
        REPO,
    ),
    APITool(
        "list_branches",
        "List branches in an accessible repository.",
        "repositories.read",
        "GET",
        "/repositories/{repo_id}/branches",
        REPO,
    ),
    APITool(
        "list_tree",
        "Browse files at a Git reference in an accessible repository.",
        "repositories.read",
        "GET",
        "/repositories/{repo_id}/tree",
        REPO,
        {"ref": REF, "path": (str, Field(default="", max_length=2000))},
    ),
    APITool(
        "read_file",
        "Read a file from an accessible repository.",
        "repositories.read",
        "GET",
        "/repositories/{repo_id}/blob",
        REPO,
        {"ref": REF, "path": (str, Field(min_length=1, max_length=2000))},
    ),
    APITool(
        "list_commits",
        "Read commit history in an accessible repository.",
        "repositories.read",
        "GET",
        "/repositories/{repo_id}/commits",
        REPO,
        {"ref": REF},
    ),
    APITool(
        "get_commit_diff",
        "Read a commit diff in an accessible repository.",
        "repositories.read",
        "GET",
        "/repositories/{repo_id}/commits/{sha}",
        {**REPO, "sha": Annotated[str, Field(pattern=r"^[a-fA-F0-9]{40}$")]},
    ),
    APITool(
        "list_tickets",
        "List issues or pull requests in an accessible repository.",
        "repositories.read",
        "GET",
        "/repositories/{repo_id}/tickets",
        REPO,
        {"kind": (Literal["issue", "pull"], "issue")},
    ),
    APITool(
        "get_ticket",
        "Read an issue or pull request and its comments.",
        "repositories.read",
        "GET",
        "/repositories/{repo_id}/tickets/{ticket_id}",
        TICKET,
    ),
    APITool(
        "get_pull_request_diff",
        "Read a pull request diff from an accessible repository.",
        "repositories.read",
        "GET",
        "/repositories/{repo_id}/tickets/{ticket_id}/diff",
        TICKET,
    ),
    APITool(
        "create_ticket",
        "Create an issue or pull request where the owner has Write access.",
        "repositories.write",
        "POST",
        "/repositories/{repo_id}/tickets",
        REPO,
        payload=TicketCreate,
    ),
    APITool(
        "comment_on_ticket",
        "Comment on an accessible issue or pull request with Write access.",
        "repositories.write",
        "POST",
        "/repositories/{repo_id}/tickets/{ticket_id}/comments",
        TICKET,
        payload=CommentInput,
    ),
    APITool(
        "set_ticket_state",
        "Close or reopen a ticket where the owner has Write access.",
        "repositories.write",
        "PUT",
        "/repositories/{repo_id}/tickets/{ticket_id}/state",
        TICKET,
        {"state": (Literal["open", "closed"], ...)},
    ),
    APITool(
        "create_repository",
        "Create a personal or organization repository using the owner's existing rights.",
        "repositories.create",
        "POST",
        "/repositories",
        payload=RepoCreate,
    ),
    APITool(
        "update_repository",
        "Update a repository where the owner has Maintain access.",
        "repositories.maintain",
        "PUT",
        "/repositories/{repo_id}",
        REPO,
        payload=RepoUpdate,
    ),
    APITool(
        "delete_repository",
        "Permanently delete a repository and its Git history with Maintain access and full-name confirmation.",
        "repositories.maintain",
        "DELETE",
        "/repositories/{repo_id}",
        REPO,
        {"confirmation": (str, Field(min_length=1, max_length=200))},
    ),
    APITool(
        "list_collaborators",
        "Read collaborator grants for an accessible repository.",
        "repositories.read",
        "GET",
        "/repositories/{repo_id}/members",
        REPO,
    ),
    APITool(
        "set_collaborator",
        "Set a repository collaborator's access with Maintain permission.",
        "repositories.maintain",
        "PUT",
        "/repositories/{repo_id}/members",
        REPO,
        payload=MemberInput,
    ),
    APITool(
        "remove_collaborator",
        "Remove a repository collaborator with Maintain permission.",
        "repositories.maintain",
        "DELETE",
        "/repositories/{repo_id}/members/{member_id}",
        {**REPO, "member_id": ID},
    ),
    APITool(
        "merge_pull_request",
        "Merge a pull request where the owner has Maintain access.",
        "repositories.maintain",
        "POST",
        "/repositories/{repo_id}/tickets/{ticket_id}/merge",
        TICKET,
    ),
]

BY_NAME = {tool.name: tool for tool in TOOLS}


def validate_arguments(db, user, tool, arguments):
    if tool.name == "delete_repository":
        from app.api import repo_data
        from app.mcp_keys import fail
        from app.repository_access import access

        repository = repo_data(db, access(db, arguments["repo_id"], user, "maintain"), user)
        expected = repository["owner"] + "/" + repository["name"]
        if arguments["confirmation"] != expected:
            fail(422, "Confirm the full owner/repository name to delete this repository.")
