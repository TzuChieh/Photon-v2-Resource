#!/usr/bin/env python3
"""Batch render all reference scenes under this directory."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """
    @brief Parse script arguments.
    """
    parser = argparse.ArgumentParser(description="Render all ref*.p2 scenes recursively.")
    parser.add_argument("--photon-cli", required=True, type=Path, help="Path to PhotonCLI executable.")
    parser.add_argument("-t", "--threads", required=True, type=int, help="Thread count passed to PhotonCLI.")
    return parser.parse_args()


def format_time(seconds: float | None) -> str:
    """
    @brief Format a duration as MM:SS or HH:MM:SS.
    """
    if seconds is None:
        return "N/A"

    seconds = max(0, int(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def estimate_remaining(total_elapsed: float, finished_count: int, total_count: int) -> float | None:
    """
    @brief Estimate total remaining time from completed scenes.
    """
    if finished_count == 0:
        return None
    return (total_elapsed / finished_count) * (total_count - finished_count)


def build_command(photon_cli: Path, scene: Path, output_base: Path, threads: int) -> list[str]:
    """
    @brief Build the PhotonCLI command for one reference scene.
    """
    return [
        str(photon_cli),
        "-s",
        str(scene),
        "-o",
        str(output_base),
        "-t",
        str(threads),
        "-of",
        "pfm",
        "--raw",
    ]


def output_images(output_base: Path) -> list[Path]:
    """
    @brief List PhotonCLI multi-output images for one output base path.
    """
    return list(output_base.parent.glob(f"{output_base.name}_*.pfm"))


def stop_process(process: subprocess.Popen) -> None:
    """
    @brief Stop a running subprocess, force-killing it if needed.
    """
    if process.poll() is not None:
        return

    # Ask the active renderer to stop, then force-kill if it does not exit.
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class Dashboard:
    """
    @brief Maintain a redrawable status block below normal log lines.
    """
    def __init__(self) -> None:
        self._line_count = 0
        self._enabled = sys.stdout.isatty()

    def log(self, message: str) -> None:
        """
        @brief Clear the dashboard and print one normal log line.
        """
        self.clear()
        print(message, flush=True)

    def update(self, lines: list[str]) -> None:
        """
        @brief Redraw the live dashboard block.
        """
        if not self._enabled:
            return

        self.clear()
        width = self._width()
        for line in lines:
            print(self._fit(line, width), flush=True)
        self._line_count = len(lines)

    def clear(self) -> None:
        """
        @brief Erase the current dashboard block from the terminal.
        """
        if not self._enabled or self._line_count == 0:
            return

        # Move back over the previous dashboard block and erase it. Logs printed
        # after this become normal scrollback above the next dashboard update.
        for _ in range(self._line_count):
            print("\x1b[1A\x1b[2K", end="")
        sys.stdout.flush()
        self._line_count = 0

    def _width(self) -> int:
        return max(1, shutil.get_terminal_size().columns)

    def _fit(self, text: str, width: int) -> str:
        """
        @brief Truncate text so each dashboard row stays on one terminal line.
        """
        if len(text) <= width:
            return text
        if width <= 3:
            return text[:width]
        return text[: width - 3] + "..."


def dashboard_lines(
    current_scene: Path,
    index: int,
    total_count: int,
    case_elapsed: float,
    total_elapsed: float,
    finished_count: int,
    succeeded_count: int,
    failed_count: int,
) -> list[str]:
    """
    @brief Build the text rows shown in the live dashboard.
    """
    avg = (total_elapsed / finished_count) if finished_count else None
    eta = estimate_remaining(total_elapsed, finished_count, total_count)

    return [
        "----- Live Status -----",
        f"Current   : [{index}/{total_count}] {current_scene}",
        f"Case time : {format_time(case_elapsed)}",
        f"Total     : elapsed={format_time(total_elapsed)} avg={format_time(avg)} eta={format_time(eta)}",
        f"Progress  : done={finished_count}/{total_count} ok={succeeded_count} failed={failed_count} remaining={total_count - finished_count}",
    ]


def main() -> int:
    """
    @brief Render all discovered reference scenes sequentially.
    """
    args = parse_args()
    photon_cli = args.photon_cli.expanduser().resolve()

    if args.threads <= 0:
        print("error: --threads/-t must be a positive integer.", file=sys.stderr)
        return 2
    if not photon_cli.is_file():
        print(f"error: PhotonCLI not found: {photon_cli}", file=sys.stderr)
        return 2

    root_dir = Path(__file__).resolve().parent
    scenes = sorted(path for path in root_dir.rglob("ref*.p2") if path.is_file())
    if not scenes:
        print(f"No ref scenes found under {root_dir}")
        return 1

    total_count = len(scenes)
    total_start = time.monotonic()
    failures: list[tuple[Path, str]] = []
    dashboard = Dashboard()

    dashboard.log(f"Found {total_count} ref scene(s) under {root_dir}")

    for index, scene in enumerate(scenes, start=1):
        case_start = time.monotonic()
        output_base = scene.with_suffix("")
        rel_scene = scene.relative_to(root_dir)

        dashboard.log(f"[START {index}/{total_count}] {rel_scene}")

        # Avoid stale images making a broken render look successful.
        for output_image in output_images(output_base):
            output_image.unlink()

        process = subprocess.Popen(
            build_command(photon_cli, scene, output_base, args.threads),
            # Keep PhotonCLI output from fighting with the live dashboard.
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            )

        try:
            while process.poll() is None:
                dashboard.update(
                    dashboard_lines(
                        current_scene=rel_scene,
                        index=index,
                        total_count=total_count,
                        case_elapsed=time.monotonic() - case_start,
                        total_elapsed=time.monotonic() - total_start,
                        finished_count=index - 1,
                        succeeded_count=(index - 1) - len(failures),
                        failed_count=len(failures),
                    )
                )
                time.sleep(1.0)
        except KeyboardInterrupt:
            dashboard.clear()
            print(f"Interrupted; stopping {rel_scene}", flush=True)
            return 130
        finally:
            # Also covers Ctrl-C or any early exit from the loop.
            stop_process(process)

        case_elapsed = time.monotonic() - case_start
        total_elapsed = time.monotonic() - total_start

        if process.returncode == 0 and not output_images(output_base):
            failure = "no output image found"
        elif process.returncode != 0:
            failure = f"exit={process.returncode}"
        else:
            failure = ""

        dashboard.clear()

        if failure:
            failures.append((rel_scene, failure))
            status = f"FAILED({failure})"
        else:
            status = "OK"

        finished_count = index
        avg = total_elapsed / finished_count

        dashboard.log(
            f"[DONE {index}/{total_count}] {status} {rel_scene} "
            f"| case={format_time(case_elapsed)} "
            f"| total={format_time(total_elapsed)} "
            f"| avg={format_time(avg)} "
            f"| remaining={total_count - finished_count}"
        )

    dashboard.clear()

    print()
    print("Render summary")
    print(f"  Total scenes: {total_count}")
    print(f"  Succeeded: {total_count - len(failures)}")
    print(f"  Failed: {len(failures)}")
    print(f"  Total time: {format_time(time.monotonic() - total_start)}")

    if failures:
        print("  Failed scenes:")
        for scene, reason in failures:
            print(f"    - {scene}: {reason}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
