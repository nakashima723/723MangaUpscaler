# Contributing

Use Python 3.11 on Windows. Create a virtual environment, install the
hash-locked release dependencies, and run the checks below before submitting a
change.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --only-binary=:all: --require-hashes -r requirements-release.txt
python -m pip check
python -m ruff check src tests examples
python -m pytest -q
```

Contributions are accepted under the repository's Apache License 2.0. Submit
only code and assets that you created or have the right to redistribute under
a compatible OSI-approved license. Do not submit user images, proprietary
models, third-party binaries, review archives, credentials, or code-signing
keys.

Changes to build scripts, dependency locks, GitHub workflows, SignPath files,
or code-signing policy require focused maintainer review because they affect
the trusted release chain. GitHub Actions submits signing requests and the
interactive project maintainer performs the required manual approval.
