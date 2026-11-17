# Engine → Pioneer USB spike

From the repository root, with Rust/Cargo, a C build toolchain and Python available:

```sh
spike=spikes/engine-rbxport
export CARGO_TARGET_DIR=/tmp/engine-rbxport-target
scratch=$(mktemp -d)
# Use an m.db copy made while Engine DJ was closed; specify IDs in playlist order.
python3 "$spike/read_engine.py" /path/to/copy/m.db '/path/to/Engine Library' 2570 1730 2569 > "$scratch/job.json"
cargo run --locked --manifest-path "$spike/Cargo.toml" -- "$scratch/job.json" "$scratch/usb"
```

`Engine Library` is the path against which Engine's stored audio paths resolve; it also supplies existing artwork. The Rust helper creates a fresh output directory and runs rbxport's verifier. For a hardware trial, copy the **contents** of the resulting `usb/` directory (including hidden files) to the root of an empty spare stick formatted for the player. Do not overwrite a working export.

The spike uses a single nested playlist, an Engine 3.0.2 snapshot, and two-marker adjusted grids. The USB BPM comes from grid spacing even if Engine's `bpmAnalyzed` display value differs. Beat index zero is assumed to be beat one of a four-beat bar. Hot cues keep their slots and labels; saved loops and an overridden main cue become memory points. Cue colors are not mapped. The helper builds Pioneer waveforms without detecting tempo or key and does not request audio transcoding.

On the player, check playlist order, playback, waveforms, displayed key, half-time BPM, downbeat alignment, and the position of a saved cue and loop. A software validation pass does not establish any of those player behaviors. Include an MP3 when checking timing: Engine and Pioneer may use different decoder lead-in conventions.

The local trial used Engine tracks `2570`, `1730`, and `2569` (FLAC, MP3, and AIFF). rbxport verified three audio files, grids and waveforms, and pyrekordbox independently read back the beat entries exactly. The audio copies had identical SHA-256 digests to the sources. The MP3 grid exported at 82.50 BPM rather than Engine's displayed 165 BPM. None of these tracks yielded exported cues or loops, so that mapping and player playback remain unverified.

The job is a throwaway hand-off, not a new library or interchange format. A USB reader and explicit Engine performance-data writeback are separate follow-up work; neither is part of this spike.
