# How the team works (humans + Claude + Gemini)

Read AGENTS.md first: it lists the hard rules. This file covers the workflow.

## Roles
- **Lead (repo owner)** assigns tasks (docs/TASKS.md), reviews every PR and clicks Merge. Nobody else merges.
- **Teammates** each own a task. Their AI agent (Claude Code or Antigravity/Gemini) writes the code, and the human runs the commands and opens the PR.
- **CI** (GitHub Actions) runs on every PR: tests and `verify` on Ubuntu and Windows, plus a Docker build and an offline run. A red CI means no merge.

## One-time setup (each teammate)
1. Accept the collaborator invite (it arrives by email or in GitHub notifications).
2. Install git, Python 3.11 and the GitHub CLI (`gh`). Then run `gh auth login` and choose GitHub.com, HTTPS, browser.
3. Clone the repo and check that it works:
   ```
   gh repo clone ibrahimerbol01-prog/auditgym && cd auditgym
   PYTHONPATH=src python -m unittest discover -s tests -q
   PYTHONPATH=src python -m auditgym.verify
   ```
   On Windows PowerShell, run `$env:PYTHONPATH="src"` first.

## Every task
```
git checkout main && git pull
git checkout -b task/T5-ui-polish          # one task = one branch
# ... work, small commits ...
PYTHONPATH=src python -m unittest discover -s tests -q
PYTHONPATH=src python -m auditgym.verify
git push -u origin task/T5-ui-polish
gh pr create --fill --base main            # then fill in the template: paste the outputs
```
Send the PR link to the lead in the chat.

## Rules that prevent conflicts
- **Touch only the files your task owns** (they are listed in docs/TASKS.md). If you need another file, ask in the PR.
- **Only one PR that changes generation (`src/auditgym/gen/`) may be open at a time.** Such a PR regenerates `episodes/`, and two of them always conflict.
- If `main` moved on, run `git pull --rebase origin main` and then rerun the tests. Do not resolve conflicts in `episodes/` by hand; run `python -m auditgym.cli build-suite` instead.
- Never force-push to `main`. Never commit `private/`, tokens or `.env`.

## Review
- The lead reviews with a model different from the author's: Claude reviews Gemini's PRs, and the reverse.
- The review checks four things: CI is green, the diff stays within the task's files, the AGENTS.md rules are kept (std-lib only, integer money, no weakened tests), and the outputs are pasted in the PR.
- The verdict is one of: **approve** (the lead merges with "Squash and merge"), **changes requested** (fix on the same branch; the PR updates itself), or **close**.

## Freeze
On Nov 22 at 18:00 Astana time, merging stops except for fixes the lead requests. Submission is at 21:00.
