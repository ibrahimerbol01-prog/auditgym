# Third-party notices

AuditGym itself is released under the MIT License (see `LICENSE`). The environment, the evaluator and the
official verification use the Python 3.11 standard library only.

The **desktop app and the `auditgym` terminal command** (the downloadable builds from `desktop/`) bundle a Python
runtime and a few libraries so that they run without Python installed. Their licences:

| Component | Used for | Licence |
|---|---|---|
| CPython 3.11 runtime, with the libraries it ships (OpenSSL, libffi, zlib, bzip2, xz, SQLite, expat) | runs the app | PSF License 2.0; the bundled libraries under their own licences, listed in Python's `LICENSE` (OpenSSL: Apache 2.0; the others: MIT, BSD-style or public domain) |
| pywebview 6.2.1 | the native app window | BSD 3-Clause |
| bottle, proxy_tools (pywebview dependencies) | | MIT |
| typing_extensions (pywebview dependency) | | PSF License 2.0 |
| pythonnet, clr_loader, cffi (Windows only) | pywebview on Windows (Edge WebView2) | MIT |
| pycparser (Windows only) | cffi dependency | BSD 3-Clause |
| PyObjC (macOS only) | pywebview on macOS (WebKit) | MIT |
| PyInstaller 6.22.3 bootloader | starts the bundled app | GPL 2.0 or later **with the bootloader exception**, which allows distributing the bundled program under its own licence (here MIT) |
| Inter, JetBrains Mono fonts | the interface | SIL Open Font License 1.1 (`fonts/OFL-*.txt` next to the interface files) |

Not bundled, provided by the operating system: Microsoft Edge WebView2 (Windows), WebKit (macOS), GTK/WebKitGTK
when present (Linux; otherwise the app opens in the default browser).

All data in AuditGym is synthetic: no real companies, people, bank records or payments.
