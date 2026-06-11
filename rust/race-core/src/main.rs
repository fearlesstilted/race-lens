/// race-core: Telemetry resampler — raw JSONL → positions.json
///
/// Usage: race-core <raw.jsonl> <track.json> <out.json> [tick_ms=500]
///
/// Reads raw positions (streaming, line-by-line), groups by driver,
/// resamples to uniform tick grid, normalises to SVG viewbox coordinates
/// using track.json extent/padding, writes compact positions.json.

use std::collections::HashMap;
use std::env;
use std::fs::File;
use std::io::{BufRead, BufReader, BufWriter, Write};
use serde::Deserialize;
use serde_json::{json, Value};

// ── Input types ─────────────────────────────────────────────────────────────

#[derive(Deserialize)]
struct RawPoint {
    driver: String,
    t_ms: i64,
    x: f32,
    y: f32,
}

#[derive(Deserialize)]
struct TrackJson {
    session_id: String,
    viewbox: [f64; 2],
    extent_dm: [f64; 4], // [x_min, y_min, x_max, y_max]
    padding: f64,
}

// ── Normalisation ────────────────────────────────────────────────────────────

/// Normalise a raw (x, y) in deci-metres to SVG viewbox coords.
/// Mirrors the Python formula in cli.py:
///   scale = min(avail_w/x_range, avail_h/y_range)
///   nx = PAD + (avail_w - x_range*scale)/2 + (x - x_min)*scale
///   ny = VH - (PAD + (avail_h - y_range*scale)/2 + (y - y_min)*scale)  ← Y-invert
pub(crate) fn normalise(x: f64, y: f64, track: &TrackJson) -> (f64, f64) {
    let vw = track.viewbox[0];
    let vh = track.viewbox[1];
    let pad = track.padding;
    let x_min = track.extent_dm[0];
    let y_min = track.extent_dm[1];
    let x_max = track.extent_dm[2];
    let y_max = track.extent_dm[3];

    let x_range = (x_max - x_min).max(1.0);
    let y_range = (y_max - y_min).max(1.0);
    let avail_w = vw - 2.0 * pad;
    let avail_h = vh - 2.0 * pad;
    let scale = (avail_w / x_range).min(avail_h / y_range);
    let offset_x = pad + (avail_w - x_range * scale) / 2.0;
    let offset_y = pad + (avail_h - y_range * scale) / 2.0;

    let nx = offset_x + (x - x_min) * scale;
    let ny = vh - (offset_y + (y - y_min) * scale); // Y-invert

    (nx, ny)
}

// ── Resampling ───────────────────────────────────────────────────────────────

/// Resample sorted (t, x, y) points onto a uniform tick grid [0..max_t] step tick_ms.
/// Gap > 5000 ms → null frame. Returns Vec<Option<(f64, f64)>>.
pub(crate) fn resample(
    points: &[(i64, f32, f32)],
    max_t: i64,
    tick_ms: i64,
    track: &TrackJson,
) -> Vec<Option<(f64, f64)>> {
    let n_ticks = (max_t / tick_ms + 1) as usize;
    let mut frames: Vec<Option<(f64, f64)>> = Vec::with_capacity(n_ticks);

    let mut idx = 0usize;

    for frame_i in 0..n_ticks {
        let t = frame_i as i64 * tick_ms;

        // Advance idx so points[idx] is the last point with t <= query t
        while idx + 1 < points.len() && points[idx + 1].0 <= t {
            idx += 1;
        }

        if points.is_empty() {
            frames.push(None);
            continue;
        }

        let (t0, x0, y0) = points[idx];

        if t < t0 {
            // Query is before first sample
            frames.push(None);
            continue;
        }

        // Check for gap
        let next_t = if idx + 1 < points.len() { points[idx + 1].0 } else { t0 };
        let gap = if idx + 1 < points.len() { next_t - t0 } else { 0 };
        if gap > 5000 && t > t0 {
            frames.push(None);
            continue;
        }

        if idx + 1 < points.len() && points[idx + 1].0 > t0 {
            let (t1, x1, y1) = points[idx + 1];
            let alpha = (t - t0) as f64 / (t1 - t0) as f64;
            let x = x0 as f64 + alpha * (x1 as f64 - x0 as f64);
            let y = y0 as f64 + alpha * (y1 as f64 - y0 as f64);
            let (nx, ny) = normalise(x, y, track);
            frames.push(Some((nx, ny)));
        } else {
            let (nx, ny) = normalise(x0 as f64, y0 as f64, track);
            frames.push(Some((nx, ny)));
        }
    }

    frames
}

// ── Main ─────────────────────────────────────────────────────────────────────

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 4 {
        eprintln!("Usage: race-core <raw.jsonl> <track.json> <out.json> [tick_ms=500]");
        std::process::exit(1);
    }

    let raw_path = &args[1];
    let track_path = &args[2];
    let out_path = &args[3];
    let tick_ms: i64 = if args.len() >= 5 {
        args[4].parse().expect("tick_ms must be integer")
    } else {
        500
    };

    // Load track.json
    let track_str = std::fs::read_to_string(track_path).expect("Cannot read track.json");
    let track: TrackJson = serde_json::from_str(&track_str).expect("Invalid track.json");

    // Stream-read raw JSONL, group by driver
    eprintln!("Reading {raw_path} …");
    let f = File::open(raw_path).expect("Cannot open raw.jsonl");
    let reader = BufReader::new(f);

    let mut driver_points: HashMap<String, Vec<(i64, f32, f32)>> = HashMap::new();

    for line in reader.lines() {
        let line = line.expect("IO error reading line");
        if line.trim().is_empty() {
            continue;
        }
        let pt: RawPoint = match serde_json::from_str(&line) {
            Ok(p) => p,
            Err(e) => {
                eprintln!("Skip bad line: {e}");
                continue;
            }
        };
        driver_points
            .entry(pt.driver)
            .or_default()
            .push((pt.t_ms, pt.x, pt.y));
    }

    eprintln!("Loaded {} drivers", driver_points.len());

    // Sort each driver by t, find global max_t
    let mut max_t: i64 = 0;
    for pts in driver_points.values_mut() {
        pts.sort_by_key(|(t, _, _)| *t);
        if let Some(&(t, _, _)) = pts.last() {
            if t > max_t {
                max_t = t;
            }
        }
    }

    eprintln!("max_t = {max_t} ms, tick_ms = {tick_ms}");

    // Resample each driver
    let mut drivers_out: HashMap<String, Vec<Value>> = HashMap::new();
    for (drv, pts) in &driver_points {
        let frames = resample(&pts, max_t, tick_ms, &track);
        let values: Vec<Value> = frames
            .into_iter()
            .map(|f| match f {
                None => Value::Null,
                Some((nx, ny)) => json!([
                    (nx * 10.0).round() / 10.0,
                    (ny * 10.0).round() / 10.0
                ]),
            })
            .collect();
        drivers_out.insert(drv.clone(), values);
    }

    let n_frames = (max_t / tick_ms + 1) as usize;
    eprintln!("Writing {out_path} ({n_frames} frames) …");

    let out_file = File::create(out_path).expect("Cannot create output file");
    let mut writer = BufWriter::new(out_file);

    let result = json!({
        "session_id": track.session_id,
        "start_ms": 0,
        "tick_ms": tick_ms,
        "viewbox": track.viewbox,
        "drivers": drivers_out,
    });

    serde_json::to_writer(&mut writer, &result).expect("JSON write error");
    writer.flush().expect("Flush error");

    eprintln!("Done. {n_frames} frames.");
}

// ── Unit tests ───────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn mock_track() -> TrackJson {
        TrackJson {
            session_id: "test".into(),
            viewbox: [600.0, 400.0],
            extent_dm: [0.0, 0.0, 1000.0, 500.0],
            padding: 20.0,
        }
    }

    #[test]
    fn test_interpolation_midpoint() {
        let pts = vec![(0, 0.0f32, 0.0f32), (1000, 1000.0, 500.0)];
        let track = mock_track();
        let frames = resample(&pts, 1000, 500, &track);
        // Frame at t=500 should be midpoint of (0,0)→(1000,500) raw
        assert_eq!(frames.len(), 3); // t=0, t=500, t=1000
        let (nx, ny) = frames[1].expect("expected Some at t=500");
        // Midpoint raw: (500, 250), normalise with scale min(560/1000, 360/500)=0.56
        // offset_x = 20 + (560-560)/2=20; nx = 20 + 500*0.56=300
        // offset_y = 20 + (360-280)/2=60; ny = 400 - (60+250*0.56)=400-200=200
        assert!((nx - 300.0).abs() < 0.5, "nx={nx}");
        assert!((ny - 200.0).abs() < 0.5, "ny={ny}");
    }

    #[test]
    fn test_gap_produces_null() {
        let pts = vec![(0, 0.0f32, 0.0f32), (10000, 500.0, 250.0)];
        let track = mock_track();
        // Gap of 10000ms > 5000ms → frames at t=500..9500 should be null
        let frames = resample(&pts, 10000, 500, &track);
        // t=0 → Some (first point exactly), t=500..9500 → None (gap), t=10000 → Some
        assert!(frames[0].is_some(), "t=0 should be Some");
        for i in 1..20 {
            assert!(frames[i].is_none(), "frame {i} should be None (gap)");
        }
        assert!(frames[20].is_some(), "t=10000 should be Some");
    }

    #[test]
    fn test_normalise_corners() {
        let track = mock_track();
        // Bottom-left raw corner → should map near (20, VH-20) = (20, 380) after Y-invert
        let (nx, ny) = normalise(0.0, 0.0, &track);
        // offset_x=20, offset_y=20+40=60, scale=min(560/1000,360/500)=0.56
        // nx = 20 + 0*0.56=20; ny = 400-(60+0*0.56)=340... wait let's verify
        // avail_w=560, avail_h=360, scale=min(0.56,0.72)=0.56
        // offset_x=20+(560-560)/2=20, offset_y=20+(360-280)/2=60
        // nx=20, ny=400-(60+0)=340
        assert!((nx - 20.0).abs() < 0.5, "nx corner={nx}");
        assert!((ny - 340.0).abs() < 0.5, "ny corner={ny}");
    }

    #[test]
    fn test_first_frame_at_t0() {
        let pts = vec![(0, 100.0f32, 200.0f32)];
        let track = mock_track();
        let frames = resample(&pts, 0, 500, &track);
        assert_eq!(frames.len(), 1);
        assert!(frames[0].is_some());
    }
}
