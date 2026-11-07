# Sable runtime assets

Sable is the bottom-right PawPal assistant launcher. The bundled PNGs preserve
the selected artwork and timing; `sable.json` describes the atlas cells,
directional sheets, posture transitions and image hashes.

Working source art, character sheets, individual frames, build scripts, studies,
reviews, earlier attempts, and candidate exports live in `art/livy/` at the
repository root. That local production folder is ignored by Git.

Runtime files: `sable.png`, `sable-left.png`, `posture.png`, and `sable.json`.
The app embeds these local images without relying on the source-art directory
or the separate art-preview server. Keep source masters and studies intact.
