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

## GitHub Actions full-suite QA

The full live suite runs through `.github/workflows/holo-full-e2e.yml`.

Maintainers can opt in a trusted same-repo PR by applying the `run-holo-full-e2e`
label. Applying the label starts one run; later pushes do not rerun the suite
while the label remains attached. To request another run, remove and reapply the
label or use `workflow_dispatch`. The workflow runs the shared 3/3 stable task
catalog on fixed macOS and Windows shard jobs in parallel, executes one task
per pytest invocation inside each shard, appends each task result to the GitHub
step summary, uploads `~/.holo`-style e2e artifacts, and writes a final pass-rate
report.

The workflow uses four shards per OS. With the current 7-task stable catalog,
that means eight desktop jobs total and roughly one to two tasks per shard. This
keeps macOS concurrency below the common five-job hosted-runner cap while still
reducing wall-clock time compared with one sequential runner per OS.

The workflow does not run with secrets on forked PRs. Use `workflow_dispatch` for
manual branch or release-candidate validation.

For release QA, run the workflow three times and compare the per-task pass
buckets. Keep tasks in HoloDesktop CI only when they pass 3/3 on both hosted
platforms; remove hard or inconsistent task fixtures from this suite until they
are consistently reliable.
