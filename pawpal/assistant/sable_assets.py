"""Load the bundled companion art without depending on local source artwork."""
import base64
import hashlib
import json
from pathlib import Path


def companion_assets(root=None):
    root = Path(root) if root else Path(__file__).parent.parent.parent / "assets" / "livy"
    manifest = json.loads((root / "sable.json").read_text(encoding="utf-8"))
    images = {}
    for name, filename in manifest["images"].items():
        content = (root / filename).read_bytes()
        if hashlib.sha256(content).hexdigest() != manifest["sha256"][name]:
            raise ValueError("Companion image does not match its manifest")
        images[name] = "data:image/png;base64," + base64.b64encode(content).decode("ascii")
    return {**manifest, "images": images}
