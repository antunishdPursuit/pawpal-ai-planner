import base64
import json
from pathlib import Path
import shutil

import pytest
from PIL import Image

from pawpal.assistant.sable_assets import companion_assets


def test_runtime_loads_from_fresh_directory_without_source_art(tmp_path):
    source = Path(__file__).parents[1] / "assets" / "livy"
    for name in ("sable.json", "sable.png", "sable-left.png", "posture.png"):
        shutil.copyfile(source / name, tmp_path / name)
    result = companion_assets(tmp_path)
    assert len(result["clips"]) == 11
    assert result["cellSize"] == [156, 128]
    for key, uri in result["images"].items():
        assert base64.b64decode(uri.split(",", 1)[1]) == (tmp_path / result_file(key)).read_bytes()
    (tmp_path / "posture.png").write_bytes(b"wrong image")
    with pytest.raises(ValueError, match="manifest"):
        companion_assets(tmp_path)


def result_file(key):
    return {"right": "sable.png", "left": "sable-left.png", "posture": "posture.png"}[key]


def test_posture_and_settle_share_exact_runtime_endpoints():
    root = Path(__file__).parents[1] / "assets" / "livy"
    manifest = json.loads((root / "sable.json").read_text())
    images = {key: Image.open(root / name).convert("RGBA") for key, name in manifest["images"].items()}
    def tile(clip, index, left=False):
        c = manifest["clips"][clip]
        row, col = c["frames"][index]
        atlas = images["posture" if c["atlas"] == "posture" else "left" if left else "right"]
        return atlas.crop((col*156, row*128, (col+1)*156, (row+1)*128)).tobytes()
    assert tile("stand", 0) == tile("awake", 0) == tile("lie", -1)
    assert tile("stand", -1) == tile("walk", 3, left=True) == tile("lie", 0)
    assert tile("settle", 0) == tile("awake", 0)
    assert tile("settle", -1) == tile("sleep", 0) == tile("wake", 0)
    assert tile("wake", -1) == tile("awake", 0)
