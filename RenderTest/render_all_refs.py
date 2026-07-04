#!/usr/bin/env python3
"""Batch render declared reference scenes under this directory."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path


VALID_OUTPUT_NAMES = {"beauty", "var"}

REF_SCENE_TO_OUTPUTS = {
    "checkerboard_emissive_quad/ref_bvpt_8192spp.p2": ("beauty", "var"),
    "checkerboard_emissive_quad/ref_bneept_8192spp.p2": ("var",),
    "cornell_box_normal_map/ref_bvpt_32768spp.p2": ("var",),
    "cornell_box_normal_map/ref_bneept_32768spp.p2": ("beauty", "var"),
    "cornell_box_normal_map/ref_pppm_10000passes.p2": ("beauty",),
    "cornell_box_with_gold_sphere/ref_bneept_32768spp.p2": ("beauty", "var"),
    "environment_map/ref_debug_bvpt_sphere_16384spp.p2": ("beauty", "var"),
    "environment_map/ref_debug_bneept_sphere_16384spp.p2": ("var",),
    "glossy_plane/ref_bvpt_1048576spp.p2": ("beauty", "var"),
    "glossy_plane/ref_bneept_1048576spp.p2": ("var",),
    "lerped_lambertian_diffuse/ref_no_lerp_bvpt_65536spp.p2": ("beauty", "var"),
    "lerped_lambertian_diffuse/ref_factor0p5_bvpt_65536spp.p2": ("var",),
    "lerped_lambertian_diffuse/ref_factor0p8_bvpt_65536spp.p2": ("var",),
    "lerped_lambertian_diffuse/ref_no_lerp_bneept_65536spp.p2": ("var",),
    "lerped_lambertian_diffuse/ref_factor0p5_bneept_65536spp.p2": ("var",),
    "masked_quad_spiral/ref_bvpt_32768spp.p2": ("beauty", "var"),
    "motion_blur_occluder/ref_bvpt_32768spp.p2": ("beauty", "var"),
    "normal_mapped_plane/ref_bvpt_32768spp.p2": ("var",),
    "normal_mapped_plane/ref_bneept_32768spp.p2": ("beauty", "var"),
    "normal_mapped_plane/ref_pppm_8192passes.p2": ("beauty",),
    "sample_generators/ref_bvpt_1000spp.p2": ("beauty",),
    "single_ply_mesh/ref_quad_bvpt_16384spp.p2": ("beauty", "var"),
    "single_ply_mesh/ref_quad_bneept_16384spp.p2": ("var",),
    "single_ply_mesh/ref_suzanne_bvpt_16384spp.p2": ("var",),
    "single_ply_mesh/ref_suzanne_bneept_16384spp.p2": ("beauty", "var"),
    "white_100W_point_light/ref_bneept_65536spp.p2": ("beauty", "var"),
    "white_100W_rect_area_light/ref_bneept_8192spp.p2": ("beauty", "var"),
    "white_100W_rect_area_light/ref_bvpt_8192spp.p2": ("var",),
    "white_100W_small_rect_area_light/ref_bneept_4096spp.p2": ("beauty", "var"),
    "white_500W_rect_area_light_side/ref_bvpt_diffuse_sphere_131072spp.p2": ("beauty", "var"),
    "white_500W_rect_area_light_side/ref_bneept_diffuse_sphere_131072spp.p2": ("var",),
    "white_500W_rect_area_light_side/ref_bvpt_glass_sphere_131072spp.p2": ("beauty", "var"),
    "white_500W_rect_area_light_side/ref_bneept_glass_sphere_131072spp.p2": ("var",),
    }


def parse_args() -> argparse.Namespace:
    """
    @brief Parse script arguments.
    """
    parser = argparse.ArgumentParser(description="Render declared reference scenes recursively.")
    parser.add_argument("--photon-cli", required=True, type=Path, help="Path to PhotonCLI executable.")
    parser.add_argument("-t", "--threads", required=True, type=int, help="Thread count passed to PhotonCLI.")
    parser.add_argument(
        "-k", "--keyword",
        action="append",
        default=[],
        help="Only render declared scenes whose relative path contains this keyword. Can be repeated.")
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


def output_stem(scene: Path, output_name: str) -> Path:
    """
    @brief Get the final output stem for one declared reference output.
    """
    return scene.with_suffix("").parent / f"{scene.stem}_{output_name}"


def output_image(scene: Path, output_name: str) -> Path:
    """
    @brief Get the final PFM path for one declared reference output.
    """
    return output_stem(scene, output_name).with_suffix(".pfm")


def output_stems_for_command(scene: Path, outputs: tuple[str, ...]) -> list[str]:
    """
    @brief Build `-o` stems in declared output order.
    """
    return [str(output_stem(scene, output)) for output in outputs]


def expected_output_images(scene: Path, outputs: tuple[str, ...]) -> list[Path]:
    """
    @brief List final images expected from one declared scene.
    """
    return [output_image(scene, output) for output in outputs]


def delete_ref_images(scenes: list[tuple[Path, tuple[str, ...]]]) -> int:
    """
    @brief Delete selected reference images before regeneration.
    """
    deleted_count = 0
    for scene, outputs in scenes:
        for ref_image in expected_output_images(scene, outputs):
            if ref_image.is_file():
                ref_image.unlink()
                deleted_count += 1
    return deleted_count


def build_command(photon_cli: Path, scene: Path, outputs: tuple[str, ...], threads: int) -> list[str]:
    """
    @brief Build the PhotonCLI command for one reference scene.
    """
    return [
        str(photon_cli),
        "-s", str(scene),
        "-o", ",".join(output_stems_for_command(scene, outputs)),
        "-t", str(threads),
        "-of", "pfm",
        "--raw",
        ]


def validate_ref_scene_map(root_dir: Path) -> list[tuple[Path, tuple[str, ...]]]:
    """
    @brief Validate and return declared reference scenes.
    """
    declared_scenes = [(root_dir / rel_scene, outputs) for rel_scene, outputs in REF_SCENE_TO_OUTPUTS.items()]
    missing_scenes = [scene for scene, _ in declared_scenes if not scene.is_file()]
    if missing_scenes:
        print("error: declared ref scenes are missing:", file=sys.stderr)
        for scene in missing_scenes:
            print(f"  {scene.relative_to(root_dir)}", file=sys.stderr)
        raise RuntimeError("missing declared ref scenes")

    declared_scene_set = {scene for scene, _ in declared_scenes}
    unmapped_scenes = sorted(
        scene for scene in root_dir.rglob("ref*.p2")
        if scene.is_file() and scene not in declared_scene_set)
    if unmapped_scenes:
        print("error: ref scenes are not listed in REF_SCENE_TO_OUTPUTS:", file=sys.stderr)
        for scene in unmapped_scenes:
            print(f"  {scene.relative_to(root_dir)}", file=sys.stderr)
        raise RuntimeError("unmapped ref scenes")

    for rel_scene, outputs in REF_SCENE_TO_OUTPUTS.items():
        if not outputs:
            raise RuntimeError(f"{rel_scene} has no declared outputs")
        for output in outputs:
            if output not in VALID_OUTPUT_NAMES:
                raise RuntimeError(f"{rel_scene} has unknown output '{output}'")

    return declared_scenes


def filter_scenes(
    scenes: list[tuple[Path, tuple[str, ...]]],
    root_dir: Path,
    keywords: list[str]) -> list[tuple[Path, tuple[str, ...]]]:
    if not keywords:
        return scenes

    selected_scenes = []
    for scene, outputs in scenes:
        rel_scene = scene.relative_to(root_dir).as_posix()
        if any(keyword in rel_scene for keyword in keywords):
            selected_scenes.append((scene, outputs))

    if not selected_scenes:
        keywords_text = ", ".join(keywords)
        raise RuntimeError(f"no declared ref scenes matched -k/--keyword: {keywords_text}")

    return selected_scenes


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
    @brief Render all declared reference scenes sequentially.
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
    try:
        scenes = validate_ref_scene_map(root_dir)
        scenes = filter_scenes(scenes, root_dir, args.keyword)
    except RuntimeError:
        return 2

    total_count = len(scenes)
    total_start = time.monotonic()
    failures: list[tuple[Path, str]] = []
    dashboard = Dashboard()

    deleted_count = delete_ref_images(scenes)
    dashboard.log(f"Deleted {deleted_count} selected ref image(s) under {root_dir}")
    dashboard.log(f"Found {total_count} declared ref scene(s) under {root_dir}")

    for index, (scene, outputs) in enumerate(scenes, start=1):
        case_start = time.monotonic()
        rel_scene = scene.relative_to(root_dir)

        dashboard.log(f"[START {index}/{total_count}] {rel_scene}")

        process = subprocess.Popen(
            build_command(photon_cli, scene, outputs, args.threads),
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

        missing_images = [image for image in expected_output_images(scene, outputs) if not image.is_file()]
        if process.returncode != 0:
            failure = f"exit={process.returncode}"
        elif missing_images:
            missing_names = ", ".join(str(image.relative_to(root_dir)) for image in missing_images)
            failure = f"missing output image(s): {missing_names}"
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
