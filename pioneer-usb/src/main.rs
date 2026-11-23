//! Writes a Pioneer USB library from a traktor-m3u-sync snapshot.
//!
//! Grid, key and cues come from the snapshot unchanged; only the waveforms are computed,
//! from the audio, and cached by file so each is analysed once. Comments are not exported;
//! the `/* a / b */` tag lists in them become My Tags.

use rbl_analysis::wave_creator::{WaveCreator, Waves};
use rbl_anlz::{
    Beat,
    cues::{ExportCue, export_colour},
    encode::{Existing, RekordboxWaves, author_with_rekordbox_waves},
};
use rbl_audio::MonoStream;
use rbl_core::musickey::{Key as MusicKey, Mode};
use rbl_export::{ExportOptions, ExportRoot, SourceMyTag, SourcePlaylist, SourceTrack};
use serde::Deserialize;
use std::{
    collections::{BTreeMap, BTreeSet, HashMap},
    error::Error,
    fs,
    path::{Path, PathBuf},
    sync::Mutex,
    thread,
    time::UNIX_EPOCH,
};

type Result<T> = std::result::Result<T, Box<dyn Error + Send + Sync>>;

const SNAPSHOT_VERSION: u32 = 2;
const MY_TAG_CATEGORY: &str = "Tags";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    version: u32,
    #[allow(dead_code)]
    library: String,
    #[allow(dead_code)]
    sha256: String,
    tracks: Vec<Track>,
    playlists: Vec<Playlist>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Track {
    database: String,
    track_id: u64,
    path: String,
    key: Option<Key>,
    grid: Vec<(f64, i64)>,
    #[serde(rename = "main_cue")]
    _main_cue: Option<f64>,
    hot_cues: BTreeMap<u32, Cue>,
    loops: BTreeMap<u32, Loop>,
    info: Info,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Key {
    tonic: u8,
    minor: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Cue {
    position: f64,
    label: String,
    color: [u8; 3],
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Loop {
    start: f64,
    end: f64,
    label: String,
    #[allow(dead_code)]
    color: [u8; 3],
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Info {
    title: String,
    artist: String,
    album: String,
    genre: String,
    label: String,
    comment: String,
    year: Option<u16>,
    duration: Option<u16>,
    bitrate: Option<u32>,
    sample_rate: Option<u32>,
    file_size: Option<u64>,
    artwork: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Playlist {
    name: String,
    tracks: Vec<(String, u64)>,
    children: Vec<Playlist>,
}

fn ms(seconds: f64) -> Result<u32> {
    let value = (seconds * 1000.0).round();
    if !(0.0..=f64::from(u32::MAX)).contains(&value) {
        return Err(format!("Time out of range: {seconds}").into());
    }
    Ok(value as u32)
}

/// Every beat of a constant-tempo-per-segment grid. A beat whose index is a multiple of four
/// is a downbeat; beats before the start of the audio are dropped.
fn beats(grid: &[(f64, i64)]) -> Result<Vec<Beat>> {
    let mut out = Vec::new();
    let mut tempo_x100 = 0;
    for pair in grid.windows(2) {
        let [(start, first), (end, last)] = [pair[0], pair[1]];
        if last <= first || end <= start {
            return Err(format!("Grid markers out of order: {grid:?}").into());
        }
        let seconds_per_beat = (end - start) / (last - first) as f64;
        tempo_x100 = u16::try_from((6000.0 / seconds_per_beat).round() as i64)?;
        for beat in first..last {
            let time = start + (beat - first) as f64 * seconds_per_beat;
            if time >= 0.0 {
                out.push(beat_at(beat, tempo_x100, time)?);
            }
        }
    }
    if let Some(&(time, beat)) = grid.last().filter(|_| grid.len() > 1) {
        out.push(beat_at(beat, tempo_x100, time)?);
    }
    Ok(out)
}

fn beat_at(beat: i64, tempo_x100: u16, time: f64) -> Result<Beat> {
    Ok(Beat {
        beat_number: u16::try_from(beat.rem_euclid(4) + 1)?,
        tempo_x100,
        time_ms: ms(time)?,
    })
}

/// The device's hot cue colour code nearest to an RGB colour.
fn colour_code(rgb: [u8; 3]) -> u8 {
    let distance = |code: u8| {
        export_colour(code, 1)
            .iter()
            .zip(rgb)
            .map(|(a, b)| (i32::from(*a) - i32::from(b)).pow(2))
            .sum::<i32>()
    };
    (1..=64).min_by_key(|code| distance(*code)).unwrap_or(0)
}

/// Mirror A as a memory cue; saved loops are memory loops.
fn cues(track: &Track) -> Result<Vec<ExportCue>> {
    let mut out = Vec::new();
    for (&slot, cue) in &track.hot_cues {
        let kind = match slot {
            1..=3 => slot,
            4..=8 => slot + 1,
            _ => return Err(format!("Hot cue slot {slot} has no Pioneer equivalent").into()),
        };
        out.push(ExportCue {
            kind: u8::try_from(kind)?,
            time_ms: ms(cue.position)?,
            color_code: colour_code(cue.color),
            comment: cue.label.clone(),
            ..Default::default()
        });
    }
    if let Some(cue) = track.hot_cues.get(&1) {
        out.push(ExportCue {
            time_ms: ms(cue.position)?,
            comment: cue.label.clone(),
            ..Default::default()
        });
    }
    for saved in track.loops.values() {
        out.push(ExportCue {
            time_ms: ms(saved.start)?,
            loop_time_ms: Some(ms(saved.end)?),
            comment: saved.label.clone(),
            ..Default::default()
        });
    }
    Ok(out)
}

/// The names in a comment's `/* a / b */` lists.
fn comment_tags(comment: &str) -> impl Iterator<Item = &str> {
    comment
        .split("/*")
        .skip(1)
        .filter_map(|rest| rest.split_once("*/").map(|(list, _)| list))
        .flat_map(|list| list.split('/'))
        .map(str::trim)
        .filter(|name| !name.is_empty())
}

/// One My Tag category holding every comment tag, with ids by name.
fn my_tags<'a>(tracks: &'a [Track]) -> (Vec<SourceMyTag>, HashMap<&'a str, u64>) {
    let names: BTreeSet<&str> = tracks
        .iter()
        .flat_map(|t| comment_tags(&t.info.comment))
        .collect();
    let mut rows = vec![SourceMyTag {
        id: 1,
        seq: 1,
        name: MY_TAG_CATEGORY.into(),
        attribute: 1,
        parent: 0,
    }];
    let mut ids = HashMap::new();
    for (seq, name) in (1..).zip(names) {
        let id = u64::from(seq) + 1;
        rows.push(SourceMyTag {
            id,
            seq,
            name: name.into(),
            attribute: 0,
            parent: 1,
        });
        ids.insert(name, id);
    }
    (rows, ids)
}

fn key_name(key: &Key) -> String {
    let mode = if key.minor { Mode::Minor } else { Mode::Major };
    MusicKey {
        pitch: key.tonic,
        mode,
    }
    .name()
}

/// Waveforms for the audio at `path`, from the cache when the file is unchanged.
fn waves(path: &Path, cache: &Path, prepared: bool) -> Result<Waves> {
    let meta = fs::metadata(path)?;
    let modified = meta.modified()?.duration_since(UNIX_EPOCH)?.as_nanos();
    let mut id = blake3::Hasher::new();
    id.update(path.as_os_str().as_encoded_bytes());
    id.update(&meta.len().to_le_bytes());
    id.update(&modified.to_le_bytes());
    let cached = cache.join(id.finalize().to_hex().as_str());
    if let Ok(bytes) = fs::read(&cached) {
        return decode_waves(&bytes);
    }
    if prepared {
        return Err(format!(
            "Prepared waveform unavailable; refresh exports: {}",
            path.display()
        )
        .into());
    }
    let mut stream = MonoStream::open(path)?;
    let mut creator = WaveCreator::new(stream.sample_rate());
    let mut frames = 0;
    while let Some((_, chunk)) = stream.next_frames() {
        frames += chunk.len();
        creator.push(chunk);
    }
    if frames == 0 {
        return Err(format!("No decoded audio: {}", path.display()).into());
    }
    let waves = creator.finish();
    let temp = cached.with_extension("tmp");
    fs::write(&temp, encode_waves(&waves))?;
    fs::rename(temp, cached)?;
    Ok(waves)
}

fn wave_fields(waves: &Waves) -> [&Vec<u8>; 7] {
    [
        &waves.pwav,
        &waves.pwv2,
        &waves.pwv3,
        &waves.pwv4,
        &waves.pwv5,
        &waves.pwv6,
        &waves.pwv7,
    ]
}

fn encode_waves(waves: &Waves) -> Vec<u8> {
    let mut out: Vec<u8> = waves.pwvc.iter().flat_map(|v| v.to_le_bytes()).collect();
    for field in wave_fields(waves) {
        out.extend(u32::try_from(field.len()).unwrap_or(u32::MAX).to_le_bytes());
        out.extend(field);
    }
    out
}

fn decode_waves(bytes: &[u8]) -> Result<Waves> {
    let mut rest = bytes;
    let mut take = |n: usize| -> Result<&[u8]> {
        if rest.len() < n {
            return Err("Truncated waveform cache".into());
        }
        let (head, tail) = rest.split_at(n);
        rest = tail;
        Ok(head)
    };
    let mut pwvc = [0; 3];
    for value in &mut pwvc {
        *value = u16::from_le_bytes(take(2)?.try_into()?);
    }
    let mut field = || -> Result<Vec<u8>> {
        let len = u32::from_le_bytes(take(4)?.try_into()?) as usize;
        Ok(take(len)?.to_vec())
    };
    let [pwav, pwv2, pwv3, pwv4, pwv5, pwv6, pwv7] = [
        field()?,
        field()?,
        field()?,
        field()?,
        field()?,
        field()?,
        field()?,
    ];
    Ok(Waves {
        pwvc,
        pwv6,
        pwv7,
        pwv4,
        pwv5,
        pwv3,
        pwav,
        pwv2,
    })
}

fn source_track(
    track: &Track,
    library: &Path,
    cache: &Path,
    tag_ids: &HashMap<&str, u64>,
    prepared: bool,
) -> Result<SourceTrack> {
    let source_path = library.join(&track.path);
    let grid = beats(&track.grid)?;
    let waves = waves(&source_path, cache, prepared)
        .map_err(|e| format!("{}: {e}", source_path.display()))?;
    let analysis = author_with_rekordbox_waves(
        "",
        &grid,
        &RekordboxWaves {
            pwav: waves.pwav,
            pwv2: waves.pwv2,
            pwvc: waves.pwvc,
            pwv3: waves.pwv3,
            pwv4: waves.pwv4,
            pwv5: waves.pwv5,
            pwv6: waves.pwv6,
            pwv7: waves.pwv7,
        },
        Existing::default(),
    );
    let info = &track.info;
    Ok(SourceTrack {
        id: track.track_id,
        title: info.title.clone(),
        artist: info.artist.clone(),
        album: info.album.clone(),
        genre: info.genre.clone(),
        label: info.label.clone(),
        year: info.year.unwrap_or(0),
        duration_sec: info.duration.unwrap_or(0),
        bitrate: info.bitrate.unwrap_or(0),
        sample_rate: info.sample_rate.unwrap_or(0),
        file_size: info.file_size.unwrap_or(0),
        key: track.key.as_ref().map(key_name).unwrap_or_default(),
        bpm_x100: grid.first().map_or(0, |beat| u32::from(beat.tempo_x100)),
        artwork: info.artwork.as_ref().map(|art| library.join(art)),
        cues: Some(cues(track)?),
        my_tags: comment_tags(&info.comment)
            .map(|name| tag_ids[name])
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect(),
        analysis: vec![
            ("DAT".into(), analysis.dat),
            ("EXT".into(), analysis.ext),
            ("2EX".into(), analysis.two_ex),
        ],
        source_path,
        ..Default::default()
    })
}

/// The playlist tree, depth first, with each list's tracks as indices into `tracks`.
fn playlists(
    nodes: &[Playlist],
    index: &HashMap<(&str, u64), usize>,
) -> Result<Vec<SourcePlaylist>> {
    fn add(
        node: &Playlist,
        parent_id: u64,
        index: &HashMap<(&str, u64), usize>,
        out: &mut Vec<SourcePlaylist>,
    ) -> Result<()> {
        if !node.children.is_empty() && !node.tracks.is_empty() {
            return Err(format!("Playlist {:?} holds both tracks and playlists", node.name).into());
        }
        let id = out.len() as u64 + 1;
        let track_indices = node
            .tracks
            .iter()
            .map(|(database, track)| {
                index
                    .get(&(database.as_str(), *track))
                    .copied()
                    .ok_or_else(|| {
                        format!("Playlist {:?} names an unknown track {track}", node.name).into()
                    })
            })
            .collect::<Result<Vec<_>>>()?;
        out.push(SourcePlaylist {
            id,
            parent_id,
            name: node.name.clone(),
            folder: !node.children.is_empty(),
            track_indices,
            ..Default::default()
        });
        for child in &node.children {
            add(child, id, index, out)?;
        }
        Ok(())
    }
    let mut out = Vec::new();
    for node in nodes {
        add(node, 0, index, &mut out)?;
    }
    Ok(out)
}

fn prepare(
    snapshot: &Snapshot,
    library: &Path,
    cache: &Path,
    tag_ids: &HashMap<&str, u64>,
    prepared: bool,
) -> Result<Vec<SourceTrack>> {
    let queue = Mutex::new(snapshot.tracks.iter().enumerate());
    let done = Mutex::new(Vec::with_capacity(snapshot.tracks.len()));
    let workers = thread::available_parallelism().map_or(1, usize::from);
    thread::scope(|scope| {
        for _ in 0..workers {
            scope.spawn(|| -> Result<()> {
                loop {
                    let Some((i, track)) = queue.lock().map_err(|e| e.to_string())?.next() else {
                        return Ok(());
                    };
                    let prepared = source_track(track, library, cache, tag_ids, prepared);
                    done.lock().map_err(|e| e.to_string())?.push((i, prepared));
                }
            });
        }
    });
    let mut done = done.into_inner().map_err(|e| e.to_string())?;
    if done.len() != snapshot.tracks.len() {
        return Err("A worker stopped before preparing every track".into());
    }
    done.sort_by_key(|(i, _)| *i);
    done.into_iter().map(|(_, track)| track).collect()
}

fn run(
    snapshot: &Path,
    library: &Path,
    destination: &Path,
    cache: &Path,
    prepared: bool,
) -> Result<()> {
    let snapshot: Snapshot = serde_json::from_slice(&fs::read(snapshot)?)?;
    if snapshot.version != SNAPSHOT_VERSION {
        return Err(format!("Unsupported snapshot version {}", snapshot.version).into());
    }
    fs::create_dir_all(destination)?;
    fs::create_dir_all(cache)?;
    let index = snapshot
        .tracks
        .iter()
        .enumerate()
        .map(|(i, t)| ((t.database.as_str(), t.track_id), i))
        .collect();
    let lists = playlists(&snapshot.playlists, &index)?;
    let (tags, tag_ids) = my_tags(&snapshot.tracks);
    let tracks = prepare(&snapshot, library, cache, &tag_ids, prepared)?;
    let options = ExportOptions {
        root: Some(ExportRoot::Standard),
        ..Default::default()
    };
    rbl_export::export_with_options(destination, &tracks, &lists, &tags, &options, &mut |_| {})?;
    let report = rbl_export::verify(destination)?;
    let entries: usize = lists.iter().map(|list| list.track_indices.len()).sum();
    if !report.is_ok()
        || report.tracks != tracks.len()
        || report.playlist_entries != entries
        || report.beat_grids != tracks.len()
        || report.detail_waveforms != tracks.len()
    {
        return Err(format!("The written library does not verify: {report:?}").into());
    }
    println!(
        "{}",
        serde_json::json!({
            "tracks": report.tracks,
            "playlists": lists.len(),
            "memberships": entries,
            "hot_cues": report.hot_cues,
            "memory_cues": report.memory_cues,
            "my_tags": tags.len() - 1,
        })
    );
    Ok(())
}

fn inspect(root: &Path) -> Result<()> {
    use rbl_export::device_library::{Format, read};
    let mode = if root.join("PIONEER/rekordbox/export.pdb").is_file() {
        Format::DeviceLibrary
    } else {
        Format::OneLibrary
    };
    let library = read(root, mode)?;
    let mut paths = HashMap::new();
    let mut playlists = Vec::new();
    for node in &library.nodes {
        let mut path: Vec<&str> = paths.get(&node.parent).cloned().unwrap_or_default();
        path.push(&node.name);
        if !node.folder {
            let tracks: Vec<_> = node
                .tracks
                .iter()
                .map(|id| {
                    let track = library
                        .track(*id)
                        .ok_or("Playlist names an unknown track")?;
                    Ok::<_, Box<dyn Error + Send + Sync>>((track.master_content_id, &track.path))
                })
                .collect::<Result<_>>()?;
            playlists.push((path.clone(), tracks));
        }
        paths.insert(node.id, path);
    }
    println!("{}", serde_json::to_string(&playlists)?);
    Ok(())
}

fn main() -> std::process::ExitCode {
    let args: Vec<PathBuf> = std::env::args_os().skip(1).map(PathBuf::from).collect();
    let result = match args.as_slice() {
        [mode, root] if mode == Path::new("inspect") => inspect(root),
        [snapshot, library, destination, cache] => {
            run(snapshot, library, destination, cache, false)
        }
        [mode, snapshot, library, destination, cache] if mode == Path::new("assemble") => {
            run(snapshot, library, destination, cache, true)
        }
        _ => {
            eprintln!(
                "usage: pioneer-usb [assemble] SNAPSHOT.json ENGINE_LIBRARY DESTINATION CACHE | inspect ROOT"
            );
            return std::process::ExitCode::from(2);
        }
    };
    match result {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("ERROR {error}");
            std::process::ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn engine_grid_becomes_every_beat_with_downbeats_on_multiples_of_four() {
        // Engine's first marker sits four beats before the audio starts.
        let grid = beats(&[(-2.0, -4), (4.0, 8)]).unwrap();
        assert_eq!(grid.len(), 9);
        assert!(grid.iter().all(|b| b.tempo_x100 == 12_000));
        assert_eq!(
            grid.first().map(|b| (b.time_ms, b.beat_number)),
            Some((0, 1))
        );
        assert_eq!(
            grid.last().map(|b| (b.time_ms, b.beat_number)),
            Some((4000, 1))
        );
        assert_eq!(
            grid.iter().map(|b| b.beat_number).collect::<Vec<_>>(),
            [1, 2, 3, 4, 1, 2, 3, 4, 1]
        );
    }

    #[test]
    fn half_time_grid_is_kept_as_engine_saved_it() {
        let grid = beats(&[(0.0, 0), (60.0, 82)]).unwrap();
        assert_eq!(grid[0].tempo_x100, 8_200);
    }

    #[test]
    fn engine_cue_slots_map_to_pioneer_kinds() {
        let mut track: Track =
            serde_json::from_str(include_str!("../../tests/fixtures/snapshot.json"))
                .map(|s: Snapshot| s.tracks.into_iter().next().unwrap())
                .unwrap();
        track.hot_cues.insert(
            4,
            Cue {
                position: 1.0,
                label: "D".into(),
                color: [255, 0, 0],
            },
        );
        assert!(
            cues(&track)
                .unwrap()
                .iter()
                .all(|cue| cue.kind != 0 || cue.loop_time_ms.is_some())
        );
        track.hot_cues.insert(
            1,
            Cue {
                position: 0.25,
                label: "Start".into(),
                color: [0, 0, 0],
            },
        );
        let kinds: Vec<_> = cues(&track)
            .unwrap()
            .iter()
            .map(|c| (c.kind, c.time_ms, c.loop_time_ms))
            .collect();
        assert_eq!(
            kinds,
            [
                (1, 250, None),
                (2, 2000, None),
                (5, 1000, None),
                (0, 250, None),
                (0, 1000, Some(2000))
            ]
        );
        track.hot_cues.insert(
            9,
            Cue {
                position: 1.0,
                label: String::new(),
                color: [0, 0, 0],
            },
        );
        assert!(cues(&track).is_err());
    }

    #[test]
    fn hot_cue_colour_is_the_nearest_device_colour() {
        for code in [1, 23, 43, 60] {
            assert_eq!(colour_code(export_colour(code, 1)), code);
        }
    }

    #[test]
    fn waveform_cache_round_trips() {
        let waves = Waves {
            pwvc: [1, 2, 3],
            pwv6: vec![6],
            pwv7: vec![7, 7],
            pwv4: vec![],
            pwv5: vec![5],
            pwv3: vec![3],
            pwav: vec![0; 400],
            pwv2: vec![2],
        };
        let back = decode_waves(&encode_waves(&waves)).unwrap();
        assert_eq!(wave_fields(&back), wave_fields(&waves));
        assert_eq!(back.pwvc, waves.pwvc);
        assert!(decode_waves(&encode_waves(&waves)[..10]).is_err());
    }

    #[test]
    fn comment_tag_lists_become_my_tags_and_the_rest_is_dropped() {
        let names: Vec<_> =
            comment_tags("1A - Energy 6 /* Groove / Peak Time */ notes /* Dub */ /* open")
                .collect();
        assert_eq!(names, ["Groove", "Peak Time", "Dub"]);
        assert_eq!(comment_tags("Visit https://x.bandcamp.com").count(), 0);
    }

    #[test]
    fn folders_cannot_hold_tracks() {
        let index = HashMap::from([(("a", 1), 0)]);
        let node = Playlist {
            name: "Mixed".into(),
            tracks: vec![("a".into(), 1)],
            children: vec![Playlist {
                name: "Child".into(),
                tracks: vec![],
                children: vec![],
            }],
        };
        assert!(playlists(&[node], &index).is_err());
    }
}
