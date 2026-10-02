# Release workflow — "push to github"

Runbook for when the user explicitly says something like "push to github" /
"release this" / "push origin main". Not run automatically, not implied by
finishing an unrelated task — see `CLAUDE.md`'s "Guardrails" section.

This is linked to the `UU-BUEM` organization and pushed to the repo
`https://github.com/UU-BUEM/occupancy`

## Steps

1. **Survey the diff since the last release.**
   - `git status`, `git diff`, `git log <last-tag>..HEAD --oneline` (last
     tag: `git describe --tags --abbrev=0`).
   - Decide whether `CHANGELOG.md`'s `[Unreleased]` section already covers
     everything, or needs updating — this repo follows [Keep a
     Changelog](https://keepachangelog.com/en/1.1.0/) +
     [SemVer](https://semver.org/); see existing entries for the
     Added/Changed/Fixed/Deprecated style.
   - Decide whether `CLAUDE.md` or `.claude/*.md` need updating for
     anything durable the diff introduced (new gotcha, new convention, a
     resolved open-item) — same judgment as any other session, not a
     mechanical step.

2. **Determine the version bump.** This repo uses `setuptools_scm`
   (`pyproject.toml`: `version_file = "src/occupancy/_version.py"`) — the
   git tag *is* the version, no version string to hand-edit elsewhere.
   Existing tags follow `vMAJOR.MINOR.PATCH` (see `git tag --list`). Pick
   the bump per CHANGELOG's SemVer convention (breaking → MAJOR,
   backward-compatible addition → MINOR, fix-only → PATCH) based on the
   actual diff — don't default to PATCH without checking.

3. **Move `[Unreleased]` → the new version heading** in `CHANGELOG.md`
   (`## [X.Y.Z] - YYYY-MM-DD`, today's date), leaving a fresh empty
   `[Unreleased]` above it. Commit doc changes (CHANGELOG + any CLAUDE.md/
   `.claude/` updates from step 1) as their own commit before tagging.

4. **Run the local CI mirror** (exact steps from
   `.github/workflows/ci.yml`, in the `occupancy_env` conda env — this
   repo has no plain `python`/`conda` on PATH by default in this
   environment; use the full interpreter path, e.g.
   `C:\Users\sahoo002\.conda\envs\occupancy_env\python.exe`, or resolve
   `conda.bat` under the anaconda install first):

   ```text
   ruff check src/ tests/
   mypy src
   pytest -q --cov=occupancy --cov-report=xml
   python -m occupancy --help
   ```

   Fix or clearly report any failure before proceeding — don't tag/push on
   a red local CI mirror. `python validate.py` (repo-root script, not part
   of CI itself) is a useful extra sanity check covering the same ground
   plus package-structure checks — see `CLAUDE.md` dev commands.

5. **Show the user a summary before pushing**: the version chosen and why,
   the CHANGELOG diff, and the local CI mirror result. This is the last
   checkpoint before an action that touches the shared remote — confirm
   before continuing unless the user has said to run this workflow fully
   autonomously.

6. **Tag and push.**

   ```text
   git tag vX.Y.Z -m "vX.Y.Z"
   git push origin main
   git push origin vX.Y.Z
   ```

   **Known gotcha (first hit 2026-08-10, `v3.1.0` push): plain `git push`
   can hang indefinitely with no error output**, even after `gh auth
   setup-git` has correctly rescoped `credential.https://github.com.helper`
   away from the system-wide `credential.helper=manager` (Git Credential
   Manager) — confirmed via `git config --list --show-origin`, the override
   was in place and correct, yet the hang still happened, twice, on two
   separate plain `git push origin <ref>` invocations (2-minute and 1-minute
   timeouts both exhausted). Read-only remote operations
   (`git ls-remote`, `git fetch`) and `gh auth status`/`gh auth token` all
   returned fast and correctly in the same session — this is specific to
   `push` (a write/auth-elevation operation), most likely GCM attempting an
   interactive (browser/credential-prompt) flow that has nothing to
   complete in this headless/background tool-execution context.
   `GIT_TERMINAL_PROMPT=0` does **not** prevent this (that only suppresses
   git's own prompts, not an external credential helper's UI).

   **Workaround that worked**: bypass the credential helper entirely by
   attaching an explicit `Authorization` header built from `gh`'s own
   cached token, run from PowerShell (not the Bash tool — it was also
   unreliable for git/gh commands in the same session, separately timing
   out/erroring; PowerShell was reliable throughout):

   ```powershell
   $token = gh auth token
   $b64 = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("x-access-token:$token"))
   git -c http.extraHeader="Authorization: Basic $b64" push origin main
   git -c http.extraHeader="Authorization: Basic $b64" push origin vX.Y.Z
   ```

   Note: piping this through `2>&1` in PowerShell will wrap git's normal
   stderr progress lines (e.g. `To https://github.com/...`) in a
   `NativeCommandError` even on success (PowerShell 5.1 native-command
   stderr quirk — see this environment's own PowerShell tool notes); check
   the actual ref-update line (`<old>..<new>  main -> main` / `* [new tag]
   vX.Y.Z -> vX.Y.Z`) rather than trusting the error categorization alone.
   If this reproduces again, worth going straight to the token-header
   approach instead of re-attempting/re-diagnosing plain `git push` first.

7. **Monitor CI on GitHub** (`gh run list --branch main --limit 1`, then
   `gh run watch <run-id>`, or `gh run watch` on the latest run) until it
   completes. Report the result (pass/fail, and which step if it failed) —
   don't just fire-and-forget the push.
