"""End-to-end tests: each call runs a real fframes script in a new process."""

import subprocess
import sys
from pathlib import Path

import pytest

import vis_reel as v


@pytest.fixture(autouse=True)
def interpreter(monkeypatch):
    monkeypatch.setenv("FFRAMES_PYTHON", sys.executable)


@pytest.fixture
def starter(tmp_path):
    return v.new(
        tmp_path / "clip.py", title='Say "hi" <&>', width=640, height=360, fps=24, duration=2
    )


def test_new_script_has_the_requested_shape(starter):
    t = v.timeline(starter)
    assert (t.width, t.height, t.fps, t.duration_frames) == (640, 360, 24, 48)
    assert t.duration_seconds == pytest.approx(2.0)


def test_new_refuses_to_overwrite_and_bad_sizes(starter, tmp_path):
    with pytest.raises(FileExistsError):
        v.new(starter)
    with pytest.raises(ValueError):
        v.new(tmp_path / "bad.py", width=0)


def test_frames_writes_one_png_per_spec(starter, tmp_path):
    shots = v.frames(starter, "0s,1s,end", tmp_path / "frames")
    assert [s.frame for s in shots] == [0, 24, 47]
    for s in shots:
        data = Path(s.path).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 1000


def test_render_encodes_every_frame(starter, tmp_path):
    out = tmp_path / "clip.mp4"
    r = v.render(starter, out)
    assert (r.start_frame, r.end_frame, r.frames) == (0, 48, 48)
    assert out.stat().st_size > 1000
    assert r.size_bytes == out.stat().st_size
    again = v.render(starter, out)
    assert again.frames == 48 and out.stat().st_size > 1000


def test_render_range(starter, tmp_path):
    r = v.render(starter, tmp_path / "part.mp4", range="1s..")
    assert (r.start_frame, r.end_frame) == (24, 48)


def test_inspect_and_strip(starter, tmp_path):
    assert v.inspect(starter).checked_frames > 0
    sheet = v.strip(starter, tmp_path / "sheet.png")
    assert len(sheet.frames) == 12 and Path(sheet.output).is_file()


def test_script_arguments_reach_the_script(tmp_path):
    script = tmp_path / "args.py"
    script.write_text(
        "import sys\n"
        "import fframes as ff\n"
        "slug = sys.argv.pop(1)\n"
        'T = ff.template(\'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">\'\n'
        '                \'<rect width="64" height="64" fill="{fill}"/></svg>\')\n'
        "class V:\n"
        "    width, height, fps, duration = 64, 64, 10, 1.0\n"
        "    def render_frame(self, frame, ctx):\n"
        "        return T(fill='#123456')\n"
        "sys.exit(ff.cli(V()) if slug == 'Ada' else 3)\n"
    )
    shots = v.frames(script, "0s", tmp_path / "out", script_args=["Ada"], renderer="cpu")
    assert Path(shots[0].path).is_file()
    with pytest.raises(v.FFramesError):
        v.frames(script, "0s", tmp_path / "out", script_args=["Bob"], renderer="cpu")


def test_fframes_errors_raise(starter, tmp_path):
    with pytest.raises(v.FFramesError, match="outside the video"):
        v.frames(starter, "99s", tmp_path)


def test_python_errors_raise_with_traceback(tmp_path):
    broken = tmp_path / "broken.py"
    broken.write_text("import fframes\nraise SystemExit(f'boom {1 + 1}')\n")
    with pytest.raises(v.FFramesError, match="boom 2"):
        v.timeline(broken)


def test_render_frame_errors_name_their_cause(starter, tmp_path):
    text = starter.read_text().replace(
        "        return FRAME(",
        "        if frame.index == 10:\n            raise ValueError('boom at frame 10')\n        return FRAME(",
        1,
    )
    starter.write_text(text)
    for call in (
        lambda: v.render(starter, tmp_path / "b.mp4"),
        lambda: v.frames(starter, "10f", tmp_path),
    ):
        with pytest.raises(v.FFramesError) as error:
            call()
        assert "ValueError: boom at frame 10" in str(error.value)
        assert "unsendable" not in str(error.value) and "\x1b" not in str(error.value)
        assert "NoRootNode" not in str(error.value)


def test_inspect_reports_missing_media(tmp_path):
    script = tmp_path / "photo.py"
    script.write_text(
        "import sys\n"
        "import fframes as ff\n"
        'T = ff.template(\'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">\'\n'
        '                \'<image href="{img}" width="64" height="64"/></svg>\')\n'
        "class V:\n"
        "    width, height, fps, duration = 64, 64, 10, 1.0\n"
        "    def render_frame(self, frame, ctx):\n"
        "        return T(img=ctx.image('nope.png'))\n"
        f"sys.exit(ff.cli(V(), media=ff.Media({str(tmp_path)!r})))\n"
    )
    found = v.inspect(script)
    assert found.checked_frames > 0
    assert any("nope.png" in f["message"] and f["severity"] == "error" for f in found.findings)
    sheet = v.strip(script, tmp_path / "sheet.png")
    assert any("nope.png" in f["message"] and f["frame"] >= 0 for f in sheet.diagnostics)


def test_scale_must_be_positive(starter, tmp_path):
    for scale in (0, -1):
        with pytest.raises(ValueError, match="scale"):
            v.frames(starter, "0s", tmp_path, scale=scale)
    assert v.frames(starter, "0s", tmp_path, scale=0.5)[0].frame == 0


def test_missing_fframes_is_explained(starter, monkeypatch, tmp_path):
    bare = tmp_path / "bare.py"
    bare.write_text("import fframes_missing_module\n")
    with pytest.raises(v.FFramesError, match="No module named"):
        v.timeline(bare)


def test_missing_script(tmp_path):
    with pytest.raises(FileNotFoundError):
        v.timeline(tmp_path / "nope.py")


def make_venv(root: Path, *, with_fframes: bool) -> Path:
    """A fake virtual environment: an interpreter file, and fframes metadata if asked."""
    venv = root / ".venv"
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("")
    site = venv / (
        "Lib/site-packages" if sys.platform == "win32" else "lib/python3.13/site-packages"
    )
    site.mkdir(parents=True)
    if with_fframes:
        (site / "fframes-0.1.0.dist-info").mkdir()
    return python


def test_find_python_takes_the_nearest_venv_with_fframes(tmp_path, monkeypatch):
    monkeypatch.delenv("FFRAMES_PYTHON")
    outer = make_venv(tmp_path, with_fframes=True)
    inner = tmp_path / "project"
    make_venv(inner, with_fframes=False)
    script = inner / "videos" / "clip.py"
    script.parent.mkdir(parents=True)
    script.write_text("")
    assert Path(v.find_python(script)) == outer
    assert v.find_python(script, "custom-python") == "custom-python"


def test_find_python_falls_back_to_an_interpreter_that_has_fframes(tmp_path, monkeypatch):
    monkeypatch.delenv("FFRAMES_PYTHON")
    make_venv(tmp_path, with_fframes=False)
    script = tmp_path / "clip.py"
    script.write_text("")
    subprocess.run([v.find_python(script), "-c", "import fframes"], check=True)


def test_find_python_takes_the_environment_of_its_own_fframes(tmp_path, monkeypatch):
    # Vis runs the extension with its shared interpreter and puts the packages of the
    # extension environment on sys.path, so sys.executable cannot import fframes.
    monkeypatch.delenv("FFRAMES_PYTHON")
    env = tmp_path / ".venv-6f2538a7da2a"
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("")
    (env / "pyvenv.cfg").write_text("home = /shared/python/bin\n")
    site = env / (
        "Lib/site-packages" if sys.platform == "win32" else "lib/python3.14/site-packages"
    )
    package = site / "fframes"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    monkeypatch.setattr(sys, "path", [str(site), *sys.path])
    monkeypatch.delitem(sys.modules, "fframes", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "shared" / "python3"))
    script = tmp_path / "project" / "clip.py"
    script.parent.mkdir()
    script.write_text("")
    assert Path(v.find_python(script)) == python
