# Live e2e suite — operational notes

Run requirements that bite:

- **Single display only.** The driver screenshots and clicks the *main* display
  (`pyautogui.screenshot()` captures only the primary screen), but keyboard input
  is global — macOS may open Spotlight or launch apps on another monitor, and the
  agent will drive windows it cannot see. Disconnect or mirror secondary displays
  before any live run.
- **Launch from a user terminal.** macOS TCC attributes Accessibility / Screen
  Recording to the responsible process; runs spawned from agent/automation
  contexts inherit a context without grants and synthetic input fails silently.
- **Linux uses the CI X11 posture.** Linux live runs require Xvfb (or another X11
  display), Openbox, Picom, a session D-Bus with AT-SPI, and the Mousepad,
  Thunar, KCalc, and Google Chrome app pack. The canonical setup is
  `.github/actions/setup-linux-desktop/action.yml`; it also starts the visible
  `Holo E2E Applications` launcher used by cold-start tasks.

## GitHub Actions full-suite QA

The full live suite runs through `.github/workflows/holo-full-e2e.yml`.

Maintainers can opt in a trusted same-repo PR by applying the `run-holo-full-e2e`
label. Applying the label starts one run; later pushes do not rerun the suite
while the label remains attached. To request another run, remove and reapply the
label or use `workflow_dispatch`. The workflow runs the shared 3/3 stable task
catalog on fixed macOS, Windows, and Ubuntu 22.04 shard jobs in parallel, executes one task
per pytest invocation inside each shard, appends each task result to the GitHub
step summary, uploads `~/.holo`-style e2e artifacts, and writes a final pass-rate
report.

The workflow uses four shards per OS. With the current 8-task stable catalog,
that means twelve desktop jobs total and two tasks per shard. This
keeps macOS concurrency below the common five-job hosted-runner cap while still
reducing wall-clock time compared with one sequential runner per OS.

The workflow does not run with secrets on forked PRs. Use `workflow_dispatch` for
manual branch or release-candidate validation.

For release QA, run the workflow three times and compare the per-task pass
buckets. Keep tasks in HoloDesktop CI only when they pass 3/3 on all three hosted
platforms; remove hard or inconsistent task fixtures from this suite until they
are consistently reliable.

## Linux local reproduction

On Ubuntu 22.04, reproduce the hosted posture by following the package and
session setup in `.github/actions/setup-linux-desktop/action.yml`, then run one
task with the normal live flags:

```bash
uv sync --all-groups
uv run pytest tests/e2e/test_live_foreground.py \
  --run-holo-live-foreground \
  --holo-live-task-ids calculator_ci_smoke \
  --holo-live-timeout 180 \
  --capture=tee-sys -q
```

This Linux lane proves the shipped x86_64 managed runtime on Ubuntu 22.04 under
X11. It does not claim Wayland, Linux ARM64, GPU, or broad distro compatibility.
