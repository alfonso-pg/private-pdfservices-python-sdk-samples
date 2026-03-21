---
name: commit-push-pr
description: Commits staged changes, pushes the branch, and opens a pull request using the GitHub MCP server. Use when the user asks to commit, push, open a PR, or ship changes for review.
---

# Commit, push, and open a pull request

Use the **GitHub MCP server** (`user-github`) for push and PR creation. Run these steps in order.

## 1. Gather repo info

- **Owner and repo**: Parse from `git remote get-url origin` (e.g. `https://github.com/owner/repo` → owner, repo). If missing, use `get_me` to get the authenticated user.
- **Current branch**: `git branch --show-current`
- **Staged files**: `git diff --name-only --cached`
- If nothing is staged, stage the files the user intends to commit (or ask which files to include).

## 2. Push via MCP

- Read the contents of each staged file from the workspace.
- Call `call_mcp_tool` with:
  - **server**: `user-github`
  - **toolName**: `push_files`
  - **arguments**: `{ "owner": "<owner>", "repo": "<repo>", "branch": "<current-branch>", "files": [ { "path": "<path>", "content": "<content>" }, ... ], "message": "<commit-message>" }`
- Use a clear commit message. Prefer verb-noun style, e.g. `Add PDF summarization script`, `Fix extraction error handling`.
- If the user has not specified a message, propose one based on the staged changes.

## 3. Create pull request via MCP

- Call `call_mcp_tool` with:
  - **server**: `user-github`
  - **toolName**: `create_pull_request`
  - **arguments**: `{ "owner": "<owner>", "repo": "<repo>", "title": "<title>", "head": "<current-branch>", "base": "main", "body": "<description>" }`
- **base**: Use the repo default branch (typically `main`); use `list_branches` if unsure.
- **body**: Follow the [pull request template](.github/PULL_REQUEST_TEMPLATE.md)—include Description, Related Issue if any, and Tasks checklist.

## Fallback: already committed locally

If changes are already committed (not just staged), `push_files` would duplicate the commit. Use `git push -u origin <branch>` instead, then create the PR via MCP `create_pull_request`.

## Notes

- This project expects PRs to follow the [pull request template](.github/PULL_REQUEST_TEMPLATE.md) and [CONTRIBUTING](.github/CONTRIBUTING.md) (CLA and code review).
- Before calling MCP tools, read the tool descriptors for `push_files` and `create_pull_request` to ensure correct parameters.
