# AuditGym desktop app

The same local UI as `python -m auditgym.cli ui`, in its own window instead of a browser tab. It works offline,
like the rest of AuditGym.

This is an optional extra. The official verification (`python -m auditgym.verify`, Docker, `--network none`) never
uses it, and `src/` stays standard-library only. The two build tools below are needed only to build the app.

## Install in one line

```powershell
irm is.gd/auditgym | iex                 # Windows (PowerShell)
```
```bash
curl -fsSL is.gd/auditgym_sh | sh        # macOS / Linux
```

The source repository is private. The **Release** workflow publishes every tagged build (zips, installers,
`SHA256SUMS.txt`) to the public, releases-only repository `ibrahimerbol01-prog/auditgym-releases`, and the two
short links point at its `releases/latest/download/install.ps1` and `install.sh`. No GitHub login is needed.

### Team: the newest CI build of a branch (before a release)

Needs the GitHub CLI (`gh auth login`). Replace `main` with a branch name in both places:
```powershell
$env:AUDITGYM_BRANCH='main'; gh api "repos/ibrahimerbol01-prog/auditgym/contents/desktop/install.ps1?ref=main" -H "Accept: application/vnd.github.raw" | Out-String | iex
```

The installer downloads the build for your system from the latest public release, checks it against
`SHA256SUMS.txt`, installs it in your user folder (no admin rights) and starts it:

| System | Installed to | Shortcut | Terminal command `auditgym` |
|---|---|---|---|
| Windows 10/11 (x64) | `%LOCALAPPDATA%\Programs\AuditGym` | Start menu → AuditGym | `…\AuditGym\cli`, added to your user PATH |
| macOS (Apple silicon) | `~/Applications/AuditGym.app` | Applications | `~/.local/share/auditgym-cli`, linked as `~/.local/bin/auditgym` |
| Linux (x64) | `~/.local/share/auditgym` | app menu, and the `auditgym-app` command | `…/auditgym/AuditGym/cli`, linked as `~/.local/bin/auditgym` |

The terminal command is the full command line without Python: open a **new** terminal after installing and run
`auditgym run-agent --policy reconcile` (live trace of every step, score card, saved for the app's «Запуски» page),
`auditgym run-agent --cmd "python my_agent.py"` for your own agent, or `auditgym --version`.

Options (environment variables): `AUDITGYM_BRANCH=<branch>` for the newest build of a branch,
`AUDITGYM_VERSION=v1.0.0` for a specific release, `AUDITGYM_NO_LAUNCH=1` to
not start it, `AUDITGYM_ZIP=<file>` to install a local build. Intel Macs and Linux on ARM have no build yet: run
from source. The builds are not code-signed, so Windows SmartScreen or macOS may ask for confirmation once.

To uninstall, delete the folder above (and the Start menu shortcut or `~/.local/share/applications/auditgym.desktop`).

## Publish a release (maintainers)

```bash
git tag v1.0.0 && git push origin v1.0.0
```

The **Release desktop app** workflow builds Windows, macOS and Linux, self-tests each build and the installer,
then publishes the release with the zips, `install.ps1`, `install.sh` and `SHA256SUMS.txt`. A release is only
needed for the stable channel: every push to `main` or `task/*` that touches `src/`, `configs/` or `desktop/` already
builds installable copies (workflow **Desktop app**; see "Newest version" above).

## Run from source

```bash
python desktop/app.py              # native window if pywebview is installed, otherwise the default browser
python desktop/app.py --browser    # always use the default browser
python desktop/app.py --smoke      # headless self-check: serves the UI, plays one episode, exits 0
```

## Build it yourself

```bash
python -m pip install -r desktop/requirements-desktop.txt    # pywebview 6.2.1, PyInstaller 6.22.3
python desktop/build.py                                      # → dist/AuditGym/ and dist/AuditGym-<os>-<arch>.zip
```

On Linux, pywebview also needs a GUI backend (for example `pip install pywebview[qt]`); without one the app opens
in the default browser.

## How it works

- `desktop/app.py` starts the existing UI server (`auditgym.env.adapters.make_http_server`) on a free port on
  127.0.0.1 and opens it in a native window. Closing the window stops the server.
- The environment starts the evaluator as a separate process (`<python> -m auditgym.eval.service`). In a built app
  `<python>` is the app itself, so the app recognises that call and runs the evaluator service, and nothing else:
  any other `-m` module is refused. The evaluator therefore stays in its own process, as in every other mode.
- The app bundles only public files: the UI, `configs/`, `report.json` and `trajectories.jsonl`. It never ships or
  reads `private/`, truth or provenance (checked by `tests/test_desktop.py`).
