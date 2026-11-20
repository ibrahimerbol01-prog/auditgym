# AuditGym desktop app

The same local UI as `python -m auditgym.cli ui`, in its own window instead of a browser tab. It works offline,
like the rest of AuditGym.

This is an optional extra. The official verification (`python -m auditgym.verify`, Docker, `--network none`) never
uses it, and `src/` stays standard-library only. The two build tools below are needed only to build the app.

## Download

Every change to `desktop/` or the UI builds the app on GitHub Actions (workflow **Desktop app**). Open the latest
run and download `AuditGym-Windows` or `AuditGym-macOS` from **Artifacts**, unzip, and start:

- **Windows:** `AuditGym\AuditGym.exe` (uses the Edge WebView2 runtime that ships with Windows 10 and 11).
  The build is not code-signed, so Windows SmartScreen may ask for confirmation the first time.
- **macOS:** `AuditGym.app` (not notarised: right-click → Open the first time).

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
