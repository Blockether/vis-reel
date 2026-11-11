---
name: fframes
description: Write, check and render videos in Python with fframes (SVG templates, timelines, audio, text, shaders, video clips). Use when a person asks for a video, an animation or a motion graphic.
---

# Make a video with fframes

A video is one Python file. It builds templates and timelines once, has a video
class with a `render_frame` method, and ends with `fframes.cli(video)`. The Rust
engine renders the frames in parallel and encodes them. Python only fills in values.

## Procedure

The tools run each script in a new process with the first interpreter of: the `python=`
argument, `$FFRAMES_PYTHON`, the nearest `.venv` above the script that has the `fframes`
package, then the interpreter of this extension, which has `fframes` installed.

1. Start from `await reel.new("videos/intro.py", title="...", duration=8)`, or from
   an example in the fframes-python repository (`examples/`).
2. Write the video (rules below).
3. Look at it: `await reel.frames("videos/intro.py", "0s,25%,50%,end")`. The PNGs
   are attached, so look at them. Fix each finding (clipped text, missing media).
4. Check the motion: `await reel.strip("videos/intro.py")`, then
   `await reel.inspect("videos/intro.py")`.
5. Render: `await reel.render("videos/intro.py", "out/intro.mp4")`. Use `draft=True`
   or `range="2s..4s"` while you iterate.

## The video object

```python
import sys
import fframes as ff
from fframes import Color, Easing, Transform

FADE = ff.timeline(((0, 1), 0.0, 1.0, Easing.EASE_OUT))  # built once
SLIDE = ff.timeline(((0.5, 1.5), Transform.translate(-400, 0), Transform.translate(0, 0)))
FRAME = ff.template("""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" width="{width}" height="{height}">
  <rect width="1920" height="1080" fill="#0f172a"/>
  <text x="960" y="540" text-anchor="middle" font-size="120" fill="#fff"
        opacity="{fade}" transform="{slide}">{title}</text>
</svg>
""")


class Intro:
    fps = 30  # default 30
    width, height = 1920, 1080
    duration = 4.0  # seconds, ff.Duration.frames(n), ff.Duration.from_audio(f) or None (auto)
    audio = [ff.AudioTrack("music.mp3").fade_out(1.0)]  # optional
    background_color = "#000"  # optional

    def render_frame(self, frame: ff.Frame, ctx: ff.Context) -> ff.Svgr:
        return FRAME(
            width=ctx.width,
            height=ctx.height,
            fade=frame.animate(FADE),
            slide=frame.animate(SLIDE),
            title="Hello",
        )


if __name__ == "__main__":
    sys.exit(ff.cli(Intro(), media=ff.Media("media")))
```

- **Scenes**: instead of `render_frame`, give the video `scenes = [A(), B()]`. Each
  scene has `duration`, `render_frame(frame, ctx)` and optionally `name` (default: the
  class name, used in time specs such as `Intro@1s`), `audio` and `overlap` (seconds
  shared with the next scene, or `(previous, next)`). A video with scenes can omit
  `duration`: it is then the sum of the scenes. In a scene,
  `frame.index` and `frame.seconds` count from the scene start; `frame.into_global()`
  gives the video time.
- **Media**: `ff.Media("media", ...)` loads images, audio, video, subtitles, Lottie and
  fonts from folders once. Refer to files by name: `<image href="{img}"/>` with
  `img=ctx.image("logo.png")`, `ff.AudioTrack("voice.wav")`.
- **Own CLI arguments**: parse them with `argparse` and `parse_known_args()`, then pass
  `[sys.argv[0], *rest]` as `ff.cli(video, argv)`.

## Templates

- `ff.template(markup)` parses SVG once. `{name}` holes fill attribute values or whole
  child nodes. A hole value can be a number, a string, a `Color`, a `Transform`, a
  `Path`, an `Image`, another `Svgr`, a list of them, or `None` (drops the attribute).
- `ff.svgr(markup, **values)` is a one-shot template; prefer `ff.template` in
  `render_frame`. Lists of `Svgr` join, `Svgr.concat(items)` too.
- Supported: the SVG elements of resvg (shapes, paths, text, gradients, filters,
  masks, clip paths, images). Static `style="..."` becomes attributes.

## Animation

- `ff.timeline(*keyframes)`: each keyframe is `(at, from, to[, easing])`. `at` is a
  start second (the tween ends at the next keyframe) or `(start, end)`. Values are
  numbers, tuples, colors (`Color` or CSS strings) or `Transform`s. Easing:
  `Easing.LINEAR`, `EASE_IN`, `EASE_OUT`, `EASE_IN_OUT`, `Easing.cubic_bezier(...)`,
  `Easing.spring(mass, stiffness, damping)`, or the names `"ease-out"` etc.
- `frame.animate(tl)` gives the value at this frame; `frame.animate_loop(tl)` repeats it.
- `Transform(translate=(x, y), rotate=deg, scale=s, skew=(x, y))`, `Transform.translate(x, y)`.
  Like SVG, rotation and scale turn around the point (0, 0): use
  `Transform(rotate=(deg, (cx, cy)))`, or put the shape at (0, 0) in a translated `<g>`.

## Text, audio, video, shaders

- `frame.text_width(ctx, text, family=, size=, weight=)`, `frame.text_fit(ctx, text, max_width, ...)`,
  `frame.text_layout(ctx, text, width=, size=, align=, x=, y=)` (wrapped lines, `.svgr()`).
- `frame.visualize_audio(ctx, "music.mp3", sample_size=512, smooth_level=3)` gives a spectrum
  list; `ff.center_spectrum_low_frequencies(spectrum)` mirrors it.
- `frame.subtitle_phrase(ctx, "talk.srt")`: the subtitle text at this frame.
- `frame.video_frame(ctx, "clip.mp4", start_from=, speed=, looping=)` gives a `VideoFrame`
  whose `.image` goes into `<image href>`. `ff.Clip("clip.mp4", 2, 6).speed(2).image(frame, ctx)`.
- `frame.play_lottie(ctx, "anim.json", x=, y=, width=, height=)` gives an `Svgr`.
- `ff.Shader.sksl(src)` / `ff.Shader.shadertoy(src)`, built once; `shader.draw(frame, {"color": Color(...)})`.
- `AudioTrack(file, start, end)` with `.volume() .fade_in() .fade_out() .offset() .pan()
  .voice() .duck_under_voice() .normalize_lufs()`.

## Speed rules

- Build templates, timelines, paths and shaders at module level or in `__init__`.
- `render_frame` only computes values and calls one template. No file reads, no image
  decoding, no per-pixel Python.
- Large repeated shapes: put them in the static part of the template; a static subtree
  is built once and shared by every frame.
- Typical speed: hundreds of 1080p frames per second on the CPU renderer. Read
  `.rendered.frames_per_second` of the `reel.render(...)` result.

## CLI

Every script has these commands: `render [-o out.mp4] [RANGE] [--draft]`, `frame SPECS -o DIR`,
`strip -o sheet.png`, `inspect`, `timeline`, `svg SPEC`, `audio`. Global options:
`--renderer cpu|skia-cpu|gpu`, `--scale 0.5`, `--json`. Time specs: `120f`, `3.2s`, `1:05.5`,
`50%`, `start`, `end`, a scene name, `Intro@1.2s`, `#3`.
