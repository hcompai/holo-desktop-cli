from __future__ import annotations

import os
import shutil
import subprocess
import tkinter as tk
from pathlib import Path


def main() -> None:
    root = tk.Tk()
    root.title("Holo E2E Applications")
    root.geometry("330x310+20+20")
    root.attributes("-topmost", False)

    heading = tk.Label(root, text="Applications", font=("Sans", 20, "bold"), pady=12)
    heading.pack(fill=tk.X)

    apps = (
        ("Mousepad", ["mousepad"]),
        ("Thunar", ["thunar", str(Path.home() / "Desktop")]),
        ("KCalc", ["kcalc"]),
        ("Google Chrome", _chrome_command()),
    )
    for label, command in apps:
        button = tk.Button(root, text=label, font=("Sans", 15), height=2, command=lambda cmd=command: _launch(cmd))
        button.pack(fill=tk.X, padx=24, pady=4)

    root.mainloop()


def _chrome_command() -> list[str]:
    binary = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if binary is None:
        return ["false"]
    profile = Path(os.environ.get("HOLO_E2E_CHROME_PROFILE", "/tmp/holo-e2e-chrome-profile"))
    profile.mkdir(parents=True, exist_ok=True)
    return [
        binary,
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-search-engine-choice-screen",
        "--disable-features=Translate",
        "about:blank",
    ]


def _launch(command: list[str]) -> None:
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


if __name__ == "__main__":
    main()
