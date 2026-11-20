# Tasks

## 1. Model and Engine codec

- [x] 1.1 Performance model with versioned JSON serialization
- [x] 1.2 Lossless Engine codec for `beatData`, `quickCues` and `loops`
- [x] 1.3 Map Engine performance data to the model and capture a snapshot from a closed database
- [x] 1.4 Round-trip every `PerformanceData` row of a live `m.db` copy byte-identically and capture its snapshot (1,097 tracks; the library has no hot cues or saved loops yet, so their mapping is covered by fixtures only)

## 2. Engine USB in the package

- [x] 2.1 `usb build` and `usb push` commands from the spike, delivering to a stick root given per run
- [x] 2.2 `services.traktor-m3u-sync.usb.<name>` build and push units in the module
- [ ] 2.2a Wire the units in nix-homelab: build after Engine analysis, push on demand
- [ ] 2.3 A playlist change reaches the stick from one trigger; a repeat push sends no audio

## 3. Pioneer export

- [x] 3.1 Playlists and Pioneer track metadata in the snapshot
- [x] 3.2 rbxport helper package consuming the snapshot
- [ ] 3.2a `usb build` for `[usb.pioneer]` running the helper into a persistent directory
- [ ] 3.3 Publication rule for Pioneer's library files
- [ ] 3.4 Export opens in rekordbox desktop with Engine's grid and cues

## 4. Engine read-back and write-back

- [x] 4.1 Read a delivered Engine stick into a snapshot
- [x] 4.2 Per-field and per-slot diff of the stick against current Engine, with an approval code
- [x] 4.3 Approved write-back to Engine through the Engine publication path, replacing the spike's review
- [ ] 4.4 One real SC6000 session's edits are shown and applied exactly

## 5. Pioneer read-back

- [ ] 5.1 Read a Pioneer stick into a snapshot on the same diff

## 6. Operator UX

- [ ] 6.1 Build, push and review actions for desktop and phone
