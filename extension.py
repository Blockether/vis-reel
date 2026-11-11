"""vis-reel: Vis tools for fframes videos written in Python: scaffold, inspect, render frames and video."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import blockether.vis.extension as vis

import vis_reel as core
from vis_reel import FrameShot, Inspection, Rendered, Timeline

MAX_ATTACHED_FRAMES = 8
MAX_ATTACHED_VIDEO_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Frames:
    shots: tuple[FrameShot, ...]
    attachment_ids: Annotated[tuple[str, ...], "Attached PNGs, in shot order"] = ()

    def __str__(self) -> str:
        lines = [f"{s.spec}: frame {s.frame} ({s.seconds:.2f} s) -> {s.path}" for s in self.shots]
        for s in self.shots:
            lines += [f"  {d.get('severity')}: {d.get('message')}" for d in s.diagnostics]
        return "\n".join(lines)


@dataclass(frozen=True)
class Video:
    rendered: Rendered
    attachment_id: Annotated[str | None, "The attached video, when it is small enough"] = None

    def __str__(self) -> str:
        return str(self.rendered)


@dataclass(frozen=True)
class Sheet:
    output: str
    frames: tuple[int, ...]
    attachment_id: str | None = None
    diagnostics: Annotated[tuple[dict, ...], "Findings, each with its frame"] = ()


def _root() -> Path:
    return vis.workspace_root()


def _path(path: str | os.PathLike[str]) -> Path:
    p = Path(path).expanduser()
    return p if p.is_absolute() else _root() / p


def _scratch(script: Path, kind: str) -> Path:
    base = Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
    return base / "vis-reel" / script.stem / kind


def _opts(script_args, renderer, scale, python, timeout_s=3600.0) -> dict:
    return {
        "script_args": tuple(script_args or ()),
        "renderer": renderer,
        "scale": scale,
        "python": python,
        "cwd": _root(),
        "timeout_s": timeout_s,
    }


def _findings(items) -> tuple[vis.ActivityBlock, ...]:
    rows = tuple(
        (str(d.get("severity", "")), str(d.get("message", "")))[:2] for d in list(items)[:50]
    )
    return (vis.ActivityTable(("Severity", "Finding"), rows),) if rows else ()


def _timeline_activity(*, phase, result, **_):
    if phase != "success":
        return None
    rows = tuple(
        (
            str(s.get("name", "")),
            str(s.get("start_seconds", s.get("start", ""))),
            str(s.get("duration_seconds", s.get("duration", ""))),
        )
        for s in result.scenes
    )
    content = (vis.ActivityTable(("Scene", "Start", "Duration"), rows),) if rows else ()
    return vis.ActivityPresentation("Read video timeline", str(result), content)


def _frames_activity(*, phase, result, **_):
    if phase != "success":
        return None
    images = tuple(
        vis.ActivityImage(aid, f"{s.spec} (frame {s.frame})")
        for s, aid in zip(result.shots, result.attachment_ids)
    )
    problems = sum(len(s.diagnostics) for s in result.shots)
    summary = f"{len(result.shots)} frames" + (f", {problems} findings" if problems else "")
    found = _findings(d for s in result.shots for d in s.diagnostics)
    return vis.ActivityPresentation("Render video frames", summary, images + found)


def _render_activity(*, phase, result, **_):
    if phase != "success":
        return None
    content = (
        (vis.ActivityVideo(result.attachment_id, Path(result.rendered.output).name),)
        if result.attachment_id
        else ()
    )
    return vis.ActivityPresentation("Render video", str(result.rendered), content)


def _inspect_activity(*, phase, result, **_):
    if phase != "success":
        return None
    summary = f"{result.checked_frames} frames checked, " + (
        "no findings" if result.is_clean else f"{len(result.findings)} findings"
    )
    return vis.ActivityPresentation("Inspect video", summary, _findings(result.findings))


def _strip_activity(*, phase, result, **_):
    if phase != "success":
        return None
    content = (
        (vis.ActivityImage(result.attachment_id, "Contact sheet"),) if result.attachment_id else ()
    )
    summary = f"{len(result.frames)} frames" + (
        f", {len(result.diagnostics)} findings" if result.diagnostics else ""
    )
    found = _findings(result.diagnostics)
    return vis.ActivityPresentation("Make contact sheet", summary, content + found)


def _new_activity(*, phase, result, **_):
    if phase != "success":
        return None
    return vis.ActivityPresentation("Create video script", str(result))


class Reel:
    """fframes videos written in Python: a script that ends with `fframes.cli(video)`.

    `script` paths are relative to the workspace. Each call runs the script in a new
    process with `python`, else `$FFRAMES_PYTHON`, else the nearest `.venv` above the
    script that has fframes, else the interpreter of this extension, which has fframes. `script_args` go to the script's own arguments (for example
    `["--slug", "Ada"]`). `renderer` is "cpu", "skia-cpu" or "gpu" (default: the
    video's own). A failed script raises `FFramesError` with the fframes error or the
    end of the traceback. Write video code with the `vis-reel/fframes` skill.
    """

    @vis.method(
        activity=vis.Activity(
            label="Read video timeline", show_start=False, render=_timeline_activity
        )
    )
    def timeline(
        self,
        script: str,
        *,
        script_args: list[str] | None = None,
        python: str | None = None,
    ) -> Timeline:
        """Size, fps, duration, scenes and audio tracks, without rendering."""
        return core.timeline(_path(script), **_opts(script_args, None, None, python, 300))

    @vis.method(
        tag="verification",
        activity=vis.Activity(label="Render video frames", render=_frames_activity),
    )
    def frames(
        self,
        script: str,
        at: Annotated[
            str, "Comma-separated time specs: 0s, 2.5s, 120f, 50%, end, a scene name, Intro@1s"
        ] = "0s,50%,end",
        output_dir: str | None = None,
        *,
        renderer: str | None = None,
        scale: Annotated[float | None, "Resolution factor, for example 0.5"] = None,
        script_args: list[str] | None = None,
        python: str | None = None,
        attach: Annotated[bool, "Attach the PNGs so that you and the person see them"] = True,
    ) -> Frames:
        """Render single frames to PNG and report problems in them (clipped text, missing media).

        Use it to look at the result before a full render. Without `output_dir`, PNGs go to
        a scratch directory. At most 8 frames are attached.
        """
        path = _path(script)
        out = _path(output_dir) if output_dir else _scratch(path, "frames")
        shots = core.frames(path, at, out, **_opts(script_args, renderer, scale, python))
        ids: list[str] = []
        if attach:
            for s in shots[:MAX_ATTACHED_FRAMES]:
                row = vis.attach(s.path, label=f"{path.stem} {s.spec}")
                ids.append(str(row["id"]))
        return Frames(shots, tuple(ids))

    @vis.method(
        tag="mutation", activity=vis.Activity(label="Render video", render=_render_activity)
    )
    def render(
        self,
        script: str,
        output: Annotated[
            str | None, "Video file; default out/<script name>.mp4 in the workspace"
        ] = None,
        *,
        range: Annotated[str | None, "Only this range: 10s..20s, ..5s, a scene name"] = None,
        draft: Annotated[bool, "Half resolution and the fastest encoder preset"] = False,
        renderer: str | None = None,
        scale: float | None = None,
        script_args: list[str] | None = None,
        python: str | None = None,
        timeout_s: float = 3600.0,
        attach: Annotated[bool, "Attach the video for the person when it is at most 64 MiB"] = True,
    ) -> Video:
        """Render and encode the video (audio mixed in). Writes `output`, replacing it."""
        path = _path(script)
        out = _path(output) if output else _root() / "out" / f"{path.stem}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        rendered = core.render(
            path,
            out,
            range=range,
            draft=draft,
            **_opts(script_args, renderer, scale, python, timeout_s),
        )
        aid = None
        if attach and Path(rendered.output).stat().st_size <= MAX_ATTACHED_VIDEO_BYTES:
            aid = str(
                vis.attach(rendered.output, label=Path(rendered.output).name, audience="user")["id"]
            )
        return Video(rendered, aid)

    @vis.method(
        tag="verification", activity=vis.Activity(label="Inspect video", render=_inspect_activity)
    )
    def inspect(
        self,
        script: str,
        *,
        script_args: list[str] | None = None,
        python: str | None = None,
    ) -> Inspection:
        """Check sampled frames for missing media and fonts, clipped text and errors, without encoding."""
        return core.inspect(_path(script), **_opts(script_args, None, None, python))

    @vis.method(activity=vis.Activity(label="Make contact sheet", render=_strip_activity))
    def strip(
        self,
        script: str,
        output: str | None = None,
        *,
        script_args: list[str] | None = None,
        python: str | None = None,
        attach: bool = True,
    ) -> Sheet:
        """One PNG with 12 labelled, evenly spaced frames: review the motion of the whole video."""
        path = _path(script)
        out = _path(output) if output else _scratch(path, "strip") / f"{path.stem}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet = core.strip(path, out, **_opts(script_args, None, None, python))
        aid = (
            str(vis.attach(sheet.output, label=f"{path.stem} contact sheet")["id"])
            if attach
            else None
        )
        return Sheet(sheet.output, sheet.frames, aid, sheet.diagnostics)

    @vis.method(
        tag="mutation",
        activity=vis.Activity(label="Create video script", show_start=False, render=_new_activity),
    )
    def new(
        self,
        path: str,
        *,
        title: str = "Hello fframes",
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        duration: Annotated[float, "Seconds"] = 5.0,
    ) -> str:
        """Write a starter video script (a timeline, a template, a video class) to `path`.

        Refuses to overwrite a file. Returns the written path.
        """
        return str(
            core.new(
                _path(path), title=title, width=width, height=height, fps=fps, duration=duration
            )
        )


PROMPT = (
    "fframes renders videos from SVG templates in Python. To make or change a video, read the "
    "`vis-reel/fframes` skill, write the script, then check it with `reel.frames` (look at "
    "the PNGs) and `reel.inspect` before `reel.render`."
)

vis.register_extension(
    vis.Extension(
        name="vis-reel",
        description="Make videos in Python with fframes: scaffold, inspect, render frames and video.",
        version="0.1.0",
        alias="reel",
        prompt=PROMPT,
        env=("FFRAMES_PYTHON", "TMPDIR"),
        symbols=[vis.Symbol(Reel(), name="reel")],
    )
)
