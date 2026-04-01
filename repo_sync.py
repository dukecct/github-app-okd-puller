#!/usr/bin/env python3
"""Clone or pull a GitHub repository using GitHub App credentials."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List

import jwt
import requests

GITHUB_API_URL = "https://api.github.com"


def getenv_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def load_private_key() -> str:
    key_inline = os.getenv("GITHUB_APP_PRIVATE_KEY")
    key_file = os.getenv("GITHUB_APP_PRIVATE_KEY_FILE")

    if key_inline:
        return key_inline

    if key_file:
        path = Path(key_file)
        if not path.exists():
            raise ValueError(f"Private key file does not exist: {path}")
        return path.read_text(encoding="utf-8")

    raise ValueError(
        "Set either GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_FILE"
    )


def create_app_jwt(app_id: str, private_key: str) -> str:
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 540,
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_installation_id(app_jwt: str, repo: str | None = None) -> str:
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Prefer the repo-specific endpoint when repo is known.
    if repo:
        repo_response = requests.get(
            f"{GITHUB_API_URL}/repos/{repo}/installation",
            headers=headers,
            timeout=30,
        )
        if repo_response.status_code < 400:
            repo_body = repo_response.json()
            repo_installation_id = repo_body.get("id")
            if repo_installation_id:
                return str(repo_installation_id)

    response = requests.get(
        f"{GITHUB_API_URL}/app/installations",
        headers=headers,
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            "Failed to list app installations "
            f"(status={response.status_code}): {response.text}"
        )

    body = response.json()
    if not isinstance(body, list) or not body:
        raise RuntimeError(
            "GitHub App has no installations available for this app credentials"
        )

    installation_id = body[0].get("id")
    if not installation_id:
        raise RuntimeError(
            f"GitHub API response did not include installation id: {json.dumps(body[0])}"
        )

    return str(installation_id)


def get_installation_token(app_jwt: str, installation_id: str) -> str:
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens"
    response = requests.post(url, headers=headers, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(
            "Failed to create installation token "
            f"(status={response.status_code}): {response.text}"
        )

    body = response.json()
    token = body.get("token")
    if not token:
        raise RuntimeError(
            f"GitHub API response did not include token: {json.dumps(body)}"
        )

    return token


def auth_repo_url(repo: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{repo}.git"


def run_git(args: List[str], cwd: Path | None = None, token: str | None = None) -> None:
    display = " ".join(args)
    if token:
        display = display.replace(token, "***")

    print(f"$ {display}")
    subprocess.run(args, cwd=cwd, check=True)


def ensure_local_branch(target_dir: Path, branch: str) -> None:
    try:
        run_git(["git", "checkout", branch], cwd=target_dir)
    except subprocess.CalledProcessError:
        # Branch may not exist locally yet; create it from origin/<branch>.
        run_git(["git", "checkout", "-b", branch, f"origin/{branch}"], cwd=target_dir)


def clone_or_pull(repo: str, target_dir: Path, branch: str, token: str) -> None:
    remote_url = auth_repo_url(repo, token)

    if (target_dir / ".git").exists():
        print(f"Repository exists at {target_dir}. Pulling latest changes.")
        run_git(["git", "remote", "set-url", "origin", remote_url], cwd=target_dir, token=token)
        run_git(["git", "fetch", "--prune", "origin"], cwd=target_dir)
        if branch:
            ensure_local_branch(target_dir, branch)
            run_git(["git", "pull", "--ff-only", "origin", branch], cwd=target_dir)
        else:
            run_git(["git", "pull", "--ff-only"], cwd=target_dir)
    else:
        print(f"Cloning repository into {target_dir}.")
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        clone_args = ["git", "clone", remote_url, str(target_dir)]
        if branch:
            clone_args = ["git", "clone", "--branch", branch, "--single-branch", remote_url, str(target_dir)]
        run_git(clone_args, token=token)


def main() -> int:
    try:
        app_id = getenv_required("GITHUB_APP_ID")
        repo = getenv_required("GITHUB_REPO")

        branch = "main"
        default_target = f"/work/{repo.split('/')[-1]}"
        target_dir = Path(os.getenv("GIT_TARGET_DIR", default_target)).resolve()

        private_key = load_private_key()
        app_jwt = create_app_jwt(app_id, private_key)
        installation_id = os.getenv("GITHUB_APP_INSTALLATION_ID") or get_installation_id(
            app_jwt,
            repo,
        )
        installation_token = get_installation_token(app_jwt, installation_id)

        clone_or_pull(repo, target_dir, branch, installation_token)
        print("Repository sync completed successfully.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
