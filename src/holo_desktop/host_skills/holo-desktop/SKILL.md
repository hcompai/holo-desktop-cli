---
name: holo-desktop
description: Sub-agent that binds to one OS window on the user's machine and drives it in the background via H Company's Holo3 VLM. If direct Holo tools are not visible, search for holo_desktop tools. In NemoClaw, call holo_desktop_launch once, then poll the same run_id until it finishes, passing attached images/files as media_paths.
---

# HoloDesktop CLI

HoloDesktop CLI runs on the user's actual computer. Most hosts expose a single tool, `holo_desktop(task: str) -> str`; NemoClaw exposes `holo_desktop_launch`, `holo_desktop_poll`, and `holo_desktop_kill` because host desktop tasks can outlive the sandbox tool-call timeout. Each task sends Holo a single `task` string; it then binds to one OS window — launching a fresh app or attaching to a running one — and opens its own screenshot-and-act loop against that window, dispatching synthesized clicks and keystrokes to it until the task is done, the step or time budget is hit, or the run is cancelled. The user's real cursor and other apps are never touched. It returns a single text answer.

In hosts with lazy tool discovery, such as NemoClaw, the only initially visible tool may be tool search. That is not a blocker. Search for `holo_desktop`, call `holo_desktop_launch` once, then call `holo_desktop_poll` with that same `run_id` until the status is `completed` or `failed`. If polling says the task is still running, poll the same `run_id` again immediately; HoloDesktop tasks can take around a minute, so keep polling rather than giving a provisional answer. Do not start another HoloDesktop task and do not ask the user to poll for you. For Telegram or other channel attachments, pass the local `media://...` path unchanged in `media_paths` and tell Holo to read the attached image or file. Do not replace an image task with typed OCR fields unless the user explicitly supplied those fields as the data to submit. Do not ask Holo to upload the attachment path unless the user or target page explicitly asks for an upload. For image-reading tasks such as receipt forms, tell Holo the attached host file is the source of truth and that it should open or preview that file if needed, rather than using stale images visible in chat history or browser tabs.

Holo is blind to the caller. It does not see the conversation, prior tool results, or earlier Holo calls. Everything it knows about the goal, the user, the situation, and what counts as success has to live in the `task` string. The caller is not a relay: it is the agent that holds context, does any synthesis, and hands Holo the part that requires actually clicking through a GUI. This is why passing the user's request verbatim is the wrong reflex — the user's wording usually elides everything they expect the calling agent to carry: which Slack workspace, who "Sarah" is, what they've been working on, what the answer should look like. Fold that in. The opposite reflex is also wrong: action verbs and message content the user actually supplied should be preserved, because Holo3 grounds well on natural human imperatives and small rewrites drift intent. Paraphrase by adding context, not by rephrasing the user's words.

Holo's domain is work that happens on the user's machine: operating native apps (Finder, Mail, Calendar, Authy, Slack, Adobe, Obsidian, IDEs, conferencing apps), navigating system UI (Settings, menu bars, dialogs), interacting with the user's logged-in sessions in their own browser profile, and observing what is currently on the screen. It is not the right tool when the answer is already reachable from a web search, an API, or the calling agent's own knowledge; when the job is file-system, shell, or code work that doesn't need a GUI; or when the user wants something written or explained in the conversation rather than done on their machine.

A trivial task (open an app, read a value) usually finishes in well under a minute; a multi-step task in an unfamiliar app can take several. Holo has its own step and time budgets and will return whatever partial result it has if it exhausts them. Treat the call as long-running: do not return a final answer to the user while Holo is still in flight, and be prepared for it to fail — time out, miss a UI element, hit a permission prompt — in which case the right move is usually to refine the task with more specifics and retry, or to surface the failure to the user. One Holo task runs at a time per machine; concurrent calls return busy.

Holo runs against one bound window in the background; the user keeps their cursor and can use other apps while it works. But the bound window is the user's real app, with their real logins and data. When the action mutates state in a way the user might regret — sending real messages, deleting, paying, changing system settings — confirm with the user first, or reframe the request as observe-and-report rather than asking Holo to change things. When Holo returns, surface its answer to the user as is, unless the task explicitly asked for synthesis with other tool output.

## Examples

These show how a casual user message becomes a self-contained task. Only the `task` string is the caller's responsibility — your host's tool-call mechanism wraps it.

User: *"send Sarah an on-my-way message in slack"*

    holo_desktop
      task: Open Slack and send a DM to Sarah Chen saying 'on my way'. Return 'sent' once the message appears in the conversation.

User: *"what's on my calendar today"*

    holo_desktop
      task: Open the Calendar app, navigate to today, and report every event with its time, title, and attendees. Don't create, edit, or delete anything. Return the events as JSON.

User: *"grab my AWS code from Authy"*

    holo_desktop
      task: Open Authy and read the current 6-digit TOTP for the 'AWS' entry. Return just the 6 digits. Do not copy to clipboard.

User: *"use this image with HoloDesktop to submit the expense form"*

    holo_desktop_launch
      task: Open the expense form and submit it using the attached receipt image. Treat the attached image file as the source of truth, open or preview it if needed, read the vendor, date, item, total, and category from that image, then return the saved confirmation.
      media_paths: ["media://inbound/<receipt>.jpg"]

    holo_desktop_poll
      run_id: <returned run_id>

User (after a long thread analyzing a paper): *"save this somewhere I'll find it"*

    holo_desktop
      task: |
        Open Obsidian and create a new note titled '2026-05-13 — Mamba-3 paper notes' in the /research vault. Paste this content into it, then return 'saved' once the file is on disk:

        <the synthesised notes you just produced>

The last example is load-bearing: the caller has already done the analytical work and only hands Holo the GUI side.
