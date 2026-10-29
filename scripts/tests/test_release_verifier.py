"""A fresh checkout has no ignored output directory; fail before any real launch."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_restart_check_initializes_output_before_owned_process_launch(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("release_verifier", scripts / "verify_m3.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)

    def boundary(*_args, **_kwargs):
        assert (tmp_path / "output").is_dir()
        raise RuntimeError("owned_launch_boundary")

    monkeypatch.setattr(
        module, "subprocess", SimpleNamespace(Popen=boundary, CREATE_NO_WINDOW=0, STDOUT=-2)
    )
    with pytest.raises(RuntimeError, match="owned_launch_boundary"):
        with module.server({}, "fresh-checkout"):
            pytest.fail("launch boundary should have stopped before a server")
