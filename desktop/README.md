# AuditGym desktop app

The same local UI as `python -m auditgym.cli ui`, in its own window instead of a browser tab. It works offline,
like the rest of AuditGym.

This is an optional extra. The official verification (`python -m auditgym.verify`, Docker, `--network none`) never
uses it, and `src/` stays standard-library only. The two build tools below are needed only to build the app.

## Install in one line

### Newest version (team): the latest build of a branch

Every push to `main` or a `task/*` branch builds the app for Windows, macOS and Linux (workflow **Desktop app**).
This installs the newest successful build of a branch, so you never wait for a release. It needs the GitHub CLI
(`gh auth login`). Replace `main` with a branch name, e.g. `task/design-and-desktop`, in **both** places:

```powershell
$env:AUDITGYM_BRANCH='main'; gh api "repos/ibrahimerbol01-prog/auditgym/contents/desktop/install.ps1?ref=main" -H "Accept: application/vnd.github.raw" | Out-String | iex
```
```bash
gh api "repos/ibrahimerbol01-prog/auditgym/contents/desktop/install.sh?ref=main" -H "Accept: application/vnd.github.raw" | AUDITGYM_BRANCH=main sh
```

The installer prints what it installed (`version: <branch> @ <commit> · built <time>`); the app shows the same in
its window title, and `AuditGym --version` prints it. Builds are kept for 30 days.

### Stable version: the latest release

While the repository is **private**, use the GitHub CLI (after `gh auth login`):

```powershell
gh release download -R ibrahimerbol01-prog/auditgym -p install.ps1 -O - | Out-String | iex    # Windows (PowerShell)
```
```bash
gh release download -R ibrahimerbol01-prog/auditgym -p install.sh -O - | sh                  # macOS / Linux
```

Once the repository is **public**, no GitHub CLI is needed:

```powershell
irm https://github.com/ibrahimerbol01-prog/auditgym/releases/latest/download/install.ps1 | iex
```
```bash
curl -fsSL https://github.com/ibrahimerbol01-prog/auditgym/releases/latest/download/install.sh | sh
```

The installer downloads the build for your system from the latest GitHub Release, checks it against
`SHA256SUMS.txt`, installs it in your user folder (no admin rights) and starts it:

| System | Installed to | Shortcut |
|---|---|---|
| Windows 10/11 (x64) | `%LOCALAPPDATA%\Programs\AuditGym` | Start menu → AuditGym |
| macOS (Apple silicon) | `~/Applications/AuditGym.app` | Applications |
| Linux (x64) | `~/.local/share/auditgym` | app menu, and the `auditgym-app` command |

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
