import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import HTTPException

from app.config import settings

MAX_OUTPUT = 2 * 1024 * 1024


def path_for(repository):
    return settings().data_dir / "repositories" / f"{repository.id}.git"


def run(path, *args, input=None, limit=MAX_OUTPUT, env=None):
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run(
                ["git", "--no-pager", "-c", "core.hooksPath=/dev/null", "-C", str(path), *args],
                input=input,
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=45,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})},
            )
        except subprocess.TimeoutExpired as error:
            raise HTTPException(408, "Git operation timed out") from error
        if result.returncode:
            raise HTTPException(
                409, "Git operation failed. Check the branch, path, or merge conflicts."
            )
        if output.tell() > limit:
            raise HTTPException(
                413, "Content is too large to display in the browser. Use a local clone."
            )
        output.seek(0)
        return output.read()


def valid_branch(value):
    if not value or value.startswith("-") or len(value) > 100:
        raise HTTPException(422, "Invalid branch name")
    result = subprocess.run(["git", "check-ref-format", "--branch", value], capture_output=True)
    if result.returncode or value.startswith("@"):
        raise HTTPException(422, "Invalid branch name")
    return value


def resolve(path, ref):
    if not ref or ref.startswith("-") or len(ref) > 200:
        raise HTTPException(422, "Invalid Git reference")
    return (
        run(path, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").decode().strip()
    )


def branches(repository):
    data = run(path_for(repository), "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    return data.decode().splitlines()


def initialize(repository, user, with_readme):
    path = path_for(repository)
    path.parent.mkdir(parents=True, exist_ok=True)
    run(
        path.parent,
        "init",
        "--bare",
        f"--initial-branch={valid_branch(repository.default_branch)}",
        str(path),
    )
    run(path, "config", "http.receivepack", "true")
    run(path, "config", "receive.denyNonFastforwards", "true")
    run(path, "config", "receive.denyDeletes", "true")
    if with_readme:
        with tempfile.TemporaryDirectory(prefix="forge-init-") as directory:
            working = Path(directory)
            run(working, "init", f"--initial-branch={repository.default_branch}")
            (working / "README.md").write_text(f"# {repository.name}\n\n{repository.description}\n")
            run(working, "add", "README.md")
            run(
                working,
                "-c",
                f"user.name={user.display_name}",
                "-c",
                f"user.email={user.email}",
                "commit",
                "-m",
                "Initial commit",
            )
            run(working, "push", str(path), repository.default_branch)


def tree(repository, ref, folder):
    path = path_for(repository)
    oid = resolve(path, ref)
    if folder:
        obj = (
            run(path, "rev-parse", "--verify", "--end-of-options", f"{oid}:{folder}")
            .decode()
            .strip()
        )
        if run(path, "cat-file", "-t", obj).strip() != b"tree":
            raise HTTPException(404, "Directory not found")
    else:
        obj = oid
    entries = []
    for row in run(path, "ls-tree", "-z", obj).split(b"\0"):
        if not row:
            continue
        meta, name = row.split(b"\t", 1)
        mode, kind, sha = meta.decode().split()
        entries.append(
            {"name": name.decode("utf-8", "replace"), "kind": kind, "mode": mode, "oid": sha}
        )
    return sorted(entries, key=lambda item: (item["kind"] != "tree", item["name"]))


def blob(repository, ref, filename):
    path = path_for(repository)
    oid = resolve(path, ref)
    obj = (
        run(path, "rev-parse", "--verify", "--end-of-options", f"{oid}:{filename}").decode().strip()
    )
    if run(path, "cat-file", "-t", obj).strip() != b"blob":
        raise HTTPException(404, "File not found")
    size = int(run(path, "cat-file", "-s", obj))
    if size > MAX_OUTPUT:
        raise HTTPException(413, "File is too large to preview")
    data = run(path, "cat-file", "blob", obj)
    try:
        text = data.decode("utf-8")
        binary = b"\0" in data
    except UnicodeDecodeError:
        text, binary = "", True
    return {"content": "" if binary else text, "binary": binary, "size": size}


def commits(repository, ref, offset=0):
    path = path_for(repository)
    oid = resolve(path, ref)
    result = run(
        path, "log", "-n", "30", f"--skip={offset}", "--format=%H%x00%s%x00%an%x00%aI", oid, "--"
    )
    records = []
    for line in result.decode("utf-8", "replace").splitlines():
        sha, subject, author, date = line.split("\0", 3)
        records.append({"sha": sha, "subject": subject, "author": author, "date": date})
    return records


def compare(repository, source, target):
    path = path_for(repository)
    source_oid = resolve(path, f"refs/heads/{valid_branch(source)}")
    target_oid = resolve(path, f"refs/heads/{valid_branch(target)}")
    return run(
        path, "diff", "--no-ext-diff", "--no-textconv", f"{target_oid}...{source_oid}", "--"
    ).decode("utf-8", "replace")


def merge(repository, ticket, user):
    path = path_for(repository)
    source = resolve(path, f"refs/heads/{valid_branch(ticket.source_branch)}")
    target = resolve(path, f"refs/heads/{valid_branch(ticket.target_branch)}")
    tree_oid = run(path, "merge-tree", "--write-tree", target, source).decode().splitlines()[0]
    identity = {
        "GIT_AUTHOR_NAME": user.display_name,
        "GIT_AUTHOR_EMAIL": user.email,
        "GIT_COMMITTER_NAME": user.display_name,
        "GIT_COMMITTER_EMAIL": user.email,
    }
    commit = (
        run(
            path,
            "commit-tree",
            tree_oid,
            "-p",
            target,
            "-p",
            source,
            input=f"Merge pull request #{ticket.id}: {ticket.title}\n".encode(),
            env=identity,
        )
        .decode()
        .strip()
    )
    run(path, "update-ref", f"refs/heads/{ticket.target_branch}", commit, target)
    return commit
