# Engine USB spike

The unattended Engine analysis job is working. Test the next step on an SC6000: a full standalone Engine USB tree generated from the closed media library, without running Sync Manager.

Use a native SQLite snapshot for this same-format transfer. The native and source databases use the same schema, so translating analysis through the playlist cache would discard fields and require re-encoding cue, grid and waveform blobs. A future Engine importer and cross-format USB exporters can share a normalized read model where translation is needed. USB read-back, in-place device reconciliation, combined rekordbox media, NixOS integration and changes to the production CLI are out of scope.

Use the current source on each run, not the older USB sample, so new tracks and changes to existing tracks are included. Keep local row IDs in the clone, give it a separate device UUID and preserve source origins. Native export uses those origins for membership resolution. Build a new tree; never update a mounted stick or overwrite an existing artifact. The first hardware trial isolates `m.db`, audio, artwork and RGB overviews from vendor-generated history, cache databases, pack records and user profiles.
