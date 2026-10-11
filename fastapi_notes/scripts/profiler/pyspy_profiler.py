#!/usr/bin/env python3

import subprocess
import shutil
import json
import datetime
import pathlib
import sys
import os
import signal

SESSION_ROOT = pathlib.Path("pyspy_sessions")


def check_pyspy():
    if shutil.which("py-spy") is None:
        print(
            "\n[ERROR] py-spy is not installed.\n"
            "Install:\n"
            "    pip install py-spy\n"
            "or\n"
            "    brew install py-spy\n"
        )
        sys.exit(1)


def run_command(cmd):
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )


def get_python_processes():
    """
    Linux/macOS implementation using ps.
    """

    result = run_command(
        ["ps", "-eo", "pid,comm,args"]
    )

    if result.returncode != 0:
        return []

    processes = []

    for line in result.stdout.splitlines()[1:]:
        line = line.strip()

        if not line:
            continue

        parts = line.split(None, 2)

        if len(parts) < 3:
            continue

        pid, comm, args = parts

        if (
            "python" in comm.lower()
            or "uvicorn" in args.lower()
            or "gunicorn" in args.lower()
            or "celery" in args.lower()
        ):
            processes.append(
                {
                    "pid": pid,
                    "command": args
                }
            )

    return processes


def select_process(processes):

    print("\nRunning Python Processes:\n")

    for idx, proc in enumerate(processes, start=1):
        print(
            f"[{idx}] PID={proc['pid']} "
            f"\n    {proc['command']}\n"
        )

    while True:

        choice = input(
            "Select process number: "
        ).strip()

        try:
            index = int(choice)

            if 1 <= index <= len(processes):
                return processes[index - 1]

        except ValueError:
            pass

        print("Invalid selection.\n")


def create_session_dir(pid):

    timestamp = datetime.datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    session_dir = (
        SESSION_ROOT /
        f"profile_{pid}_{timestamp}"
    )

    session_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    return session_dir


def save_metadata(
    session_dir,
    process_info,
    profile_type
):

    metadata = {
        "timestamp": datetime.datetime.now().isoformat(),
        "pid": process_info["pid"],
        "command": process_info["command"],
        "profile_type": profile_type,
    }

    with open(
        session_dir / "metadata.json",
        "w"
    ) as f:
        json.dump(
            metadata,
            f,
            indent=4
        )


def profile_top(pid):

    print(
        "\nLaunching py-spy top.\n"
        "Press Ctrl+C to stop.\n"
    )

    subprocess.run(
        [
            "py-spy",
            "top",
            "--pid",
            str(pid)
        ]
    )


def profile_dump(pid, session_dir):

    outfile = session_dir / "stack_dump.txt"

    print(
        f"\nSaving stack dump:\n{outfile}\n"
    )

    result = run_command(
        [
            "py-spy",
            "dump",
            "--pid",
            str(pid)
        ]
    )

    with open(outfile, "w") as f:
        f.write(result.stdout)

    print("Done.")


def profile_record(pid, session_dir):

    output_file = (
        session_dir /
        "flamegraph.svg"
    )

    print(
        "\nRecording flame graph.\n"
        "Generate traffic now.\n"
        "Press Ctrl+C when done.\n"
    )

    process = subprocess.Popen(
        [
            "py-spy",
            "record",
            "-o",
            str(output_file),
            "--pid",
            str(pid),
        ]
    )

    try:
        process.wait()

    except KeyboardInterrupt:

        process.send_signal(
            signal.SIGINT
        )

        process.wait()

    print(
        f"\nFlame graph saved:\n"
        f"{output_file}\n"
    )


def menu():

    print(
        "\n==========="
        "\nPY-SPY TOOL"
        "\n===========\n"
    )

    print("[1] Live Top View")
    print("[2] Record Flame Graph")
    print("[3] Stack Dump")
    print("[4] Exit\n")

    while True:

        choice = input(
            "Select option: "
        ).strip()

        if choice in {
            "1",
            "2",
            "3",
            "4"
        }:
            return choice

        print("Invalid option.")


def main():

    check_pyspy()

    SESSION_ROOT.mkdir(
        exist_ok=True
    )

    processes = get_python_processes()

    if not processes:
        print(
            "\nNo Python processes found."
        )
        return

    process_info = select_process(
        processes
    )

    pid = process_info["pid"]

    while True:

        choice = menu()

        if choice == "4":
            return

        session_dir = create_session_dir(
            pid
        )

        if choice == "1":

            save_metadata(
                session_dir,
                process_info,
                "top"
            )

            profile_top(pid)

        elif choice == "2":

            save_metadata(
                session_dir,
                process_info,
                "record"
            )

            profile_record(
                pid,
                session_dir
            )

        elif choice == "3":

            save_metadata(
                session_dir,
                process_info,
                "dump"
            )

            profile_dump(
                pid,
                session_dir
            )


if __name__ == "__main__":
    main()