# vis-reel

Make videos in Python with [fframes](https://fframes.studio) in [Vis](https://github.com/Blockether/vis).
The agent writes a video script, looks at its frames, checks it and renders it. The Rust engine
of fframes renders the frames in parallel and encodes them; Python only fills in values.

## Install

```bash
vis-agent extension install 'blockether/vis-reel' --global --trust
```

Vis installs the prebuilt [fframes wheel](https://github.com/Blockether/fframes-python/releases)
of your platform with the extension. It holds its own FFmpeg and codec libraries:

| Platform | Requirement |
| --- | --- |
| macOS, Apple silicon | macOS 15 or later |
| Windows x64 | Windows 10 or later |
| Linux x86_64 | glibc 2.35 or later (Ubuntu 22.04, Debian 12, Fedora 36) |
| Linux arm64 | glibc 2.35 or later |

## Tools

```python
await reel.new("videos/intro.py", title="Hello", duration=8)    # a starter script
await reel.timeline("videos/intro.py")                         # size, fps, scenes, audio
await reel.frames("videos/intro.py", "0s,25%,50%,end")          # PNGs, attached
await reel.strip("videos/intro.py")                            # 12 frames on one sheet
await reel.inspect("videos/intro.py")                          # missing media, clipped text
await reel.render("videos/intro.py", "out/intro.mp4", draft=True)
```

The skill `vis-reel/fframes` tells the agent how to write a video script.

A video script is a Python file that ends with `fframes.cli(video)`. Each tool runs it in a new
process with the first interpreter of: the `python=` argument, `$FFRAMES_PYTHON`, the nearest
`.venv` above the script that has `fframes` installed, then the interpreter of this extension.

## Development

```bash
uv sync
uv run --with pytest pytest tests -q
uv run --with ruff ruff format . && uv run --with ruff ruff check .
```

A `v*` tag that matches the version in `pyproject.toml` and `extension.py` publishes a release.
