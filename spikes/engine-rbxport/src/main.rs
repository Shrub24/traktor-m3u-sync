use rbl_analysis::wave_creator::WaveCreator;
use rbl_anlz::{
    cues::ExportCue,
    encode::{Existing, RekordboxWaves, author_with_rekordbox_waves, beat_grid_of},
};
use rbl_audio::MonoStream;
use rbl_export::{ExportOptions, ExportRoot, SourcePlaylist, SourceTrack};
use serde::Deserialize;
use std::{
    error::Error,
    fs,
    path::{Path, PathBuf},
};

#[derive(Deserialize)]
struct Job {
    playlist: String,
    tracks: Vec<Track>,
}

#[derive(Deserialize)]
struct Track {
    id: u64,
    source_path: PathBuf,
    title: String,
    artist: String,
    album: String,
    key: String,
    bpm_x100: u16,
    beats: Vec<(u16, u16, u32)>,
    cues: Vec<Cue>,
    artwork: Option<PathBuf>,
}

#[derive(Deserialize)]
struct Cue {
    kind: u8,
    time_ms: u32,
    loop_time_ms: Option<u32>,
    comment: String,
}

fn prepare(track: Track) -> Result<SourceTrack, Box<dyn Error>> {
    let mut stream = MonoStream::open(&track.source_path)?;
    let sample_rate = stream.sample_rate();
    let mut creator = WaveCreator::new(sample_rate);
    let mut count = 0;
    while let Some((_, frames)) = stream.next_frames() {
        count += frames.len();
        creator.push(frames);
    }
    if count == 0 {
        return Err(format!("No decoded audio: {}", track.source_path.display()).into());
    }
    let wave = creator.finish();
    let analysis = author_with_rekordbox_waves(
        "",
        &beat_grid_of(track.beats),
        &RekordboxWaves {
            pwav: wave.pwav,
            pwv2: wave.pwv2,
            pwvc: wave.pwvc,
            pwv3: wave.pwv3,
            pwv4: wave.pwv4,
            pwv5: wave.pwv5,
            pwv6: wave.pwv6,
            pwv7: wave.pwv7,
        },
        Existing::default(),
    );
    Ok(SourceTrack {
        id: track.id,
        source_path: track.source_path,
        title: track.title,
        artist: track.artist,
        album: track.album,
        key: track.key,
        bpm_x100: u32::from(track.bpm_x100),
        duration_sec: u16::try_from(count / sample_rate as usize)?,
        sample_rate,
        artwork: track.artwork,
        analysis: vec![
            ("DAT".into(), analysis.dat),
            ("EXT".into(), analysis.ext),
            ("2EX".into(), analysis.two_ex),
        ],
        cues: Some(
            track
                .cues
                .into_iter()
                .map(|cue| ExportCue {
                    kind: cue.kind,
                    time_ms: cue.time_ms,
                    loop_time_ms: cue.loop_time_ms,
                    comment: cue.comment,
                    ..Default::default()
                })
                .collect(),
        ),
        ..Default::default()
    })
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let [job, destination] = args.as_slice() else {
        return Err("usage: engine-rbxport-spike JOB.json NEW_DIRECTORY".into());
    };
    let destination = Path::new(destination);
    fs::create_dir(destination)?;
    let job: Job = serde_json::from_slice(&fs::read(job)?)?;
    let tracks = job
        .tracks
        .into_iter()
        .map(prepare)
        .collect::<Result<Vec<_>, _>>()?;
    let playlists = [
        SourcePlaylist {
            id: 1,
            name: "Engine spike".into(),
            folder: true,
            ..Default::default()
        },
        SourcePlaylist {
            id: 2,
            parent_id: 1,
            name: job.playlist,
            track_indices: (0..tracks.len()).collect(),
            ..Default::default()
        },
    ];
    rbl_export::export_with_options(
        destination,
        &tracks,
        &playlists,
        &[],
        &ExportOptions {
            root: Some(ExportRoot::Standard),
            ..Default::default()
        },
        &mut |_| {},
    )?;
    let report = rbl_export::verify(destination)?;
    if !report.is_ok()
        || report.tracks != tracks.len()
        || report.playlist_entries != tracks.len()
        || report.beat_grids != tracks.len()
        || report.detail_waveforms != tracks.len()
    {
        return Err(format!("Incomplete USB tree: {report:?}").into());
    }
    println!("{report:?}");
    Ok(())
}
