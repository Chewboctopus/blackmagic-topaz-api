"""Topaz Video AI API engine for DaVinci Resolve.

Handles FFmpeg extraction, Topaz API communication (upload, poll, download),
and safety-frame padding. Designed to be imported by Topaz_Batch_Timeline.py.
"""
import sys
import os
import time
import json
import requests
import subprocess

CONFIG_FILE = os.path.expanduser("~/.topaz_resolve_config.json")

def get_api_key():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("api_key", "")
        except (IOError, json.JSONDecodeError):
            pass
    return ""

def save_api_key(api_key):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"api_key": api_key}, f)
        os.chmod(CONFIG_FILE, 0o600)  # owner read/write only
    except IOError:
        pass

def get_ffprobe_path():
    for p in ["/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe"]:
        if os.path.exists(p):
            return p
    return "ffprobe"

def probe_video(input_path):
    """Get video metadata via ffprobe."""
    probe_cmd = [
        get_ffprobe_path(), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=nb_frames,r_frame_rate,width,height",
        "-of", "json", input_path
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    data = json.loads(result.stdout)
    stream = data['streams'][0]

    width = int(stream['width'])
    height = int(stream['height'])
    try:
        nb_frames = int(stream['nb_frames'])
    except (ValueError, KeyError):
        # Fallback: count frames directly (slower but accurate)
        nb_frames = _count_frames(input_path)

    fps_parts = stream['r_frame_rate'].split('/')
    fps = float(fps_parts[0]) / float(fps_parts[1])
    duration = nb_frames / fps
    file_size = os.path.getsize(input_path)

    return width, height, nb_frames, fps, duration, file_size


def _count_frames(input_path):
    """Count frames via ffprobe -count_frames (slower but reliable fallback)."""
    cmd = [
        get_ffprobe_path(), "-v", "error",
        "-select_streams", "v:0",
        "-count_frames",
        "-show_entries", "stream=nb_read_frames",
        "-of", "csv=p=0", input_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                stdin=subprocess.DEVNULL, timeout=300)
        return int(result.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired):
        return 100  # last resort fallback


def get_ffmpeg_path():
    for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if os.path.exists(p):
            return p
    return "ffmpeg"

def extract_clip(input_path, output_path, source_start_frame, source_duration_frames, fps, handles=0):
    """Extract a portion of the source clip using FFmpeg. Runs synchronously.

    Uses frame-accurate re-encoding (not stream copy) to ensure precise
    frame boundaries. This avoids corrupt output from GOP keyframe misalignment.

    Args:
        source_start_frame: Frame offset from the start of the source media (GetLeftOffset)
        source_duration_frames: Number of source frames used by the clip
        fps: Frame rate of the source
        handles: Extra frames to grab on each side
    """
    start_frame = max(0, source_start_frame - handles)
    total_frames = source_duration_frames + (handles * 2)
    # Clamp: don't request frames before 0
    if source_start_frame - handles < 0:
        total_frames = source_duration_frames + handles + source_start_frame

    start_sec = start_frame / float(fps)
    duration_sec = total_frames / float(fps)

    # Always output as mp4 for compatibility
    output_base = os.path.splitext(output_path)[0]
    output_path = output_base + ".mp4"

    cmd = [
        get_ffmpeg_path(), "-y", "-nostdin",
        "-ss", str(start_sec),
        "-i", input_path,
        "-t", str(duration_sec),
        "-c:v", "libx264", "-crf", "16", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-an",  # no audio needed for Topaz
        output_path
    ]

    result = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=600
    )
    if result.returncode != 0:
        raise Exception("FFmpeg failed (code %d): %s" % (result.returncode, result.stderr[-300:]))

def pad_clip_with_safety_frames(input_path, output_path, fps, pad_frames=2):
    """Pad a clip with repeated frames at head and tail to guard against Topaz frame drops.

    Duplicates the first `pad_frames` frames at the beginning and the last
    `pad_frames` frames at the end.  Uses a filter_complex that:
      1. Extracts the first frame, loops it `pad_frames` times  (head pad)
      2. Passes the original clip through unchanged               (body)
      3. Extracts the last frame, loops it `pad_frames` times     (tail pad)
      4. Concatenates head + body + tail

    Returns the number of frames that were padded on each side (always `pad_frames`).
    """
    # Duration of one frame
    frame_dur = 1.0 / float(fps)

    # Build the filter graph
    # [0:v] is the input
    # head: grab frame 0, loop it pad_frames times
    # body: full original clip
    # tail: grab last frame, loop it pad_frames times
    filter_complex = (
        # Head: trim first frame, loop it
        "[0:v]trim=start=0:end={fd},setpts=PTS-STARTPTS,loop={loops}:{loop_size}:0,setpts=N/{fps}/TB[head];"
        # Body: full original
        "[0:v]setpts=PTS-STARTPTS[body];"
        # Tail: trim last frame, loop it
        "[0:v]reverse,trim=start=0:end={fd},setpts=PTS-STARTPTS,loop={loops}:{loop_size}:0,setpts=N/{fps}/TB[tail];"
        # Concat
        "[head][body][tail]concat=n=3:v=1:a=0[out]"
    ).format(
        fd=frame_dur,
        loops=pad_frames - 1,   # loop filter adds N *extra* loops (original + N = total)
        loop_size=1,
        fps=fps
    )

    cmd = [
        get_ffmpeg_path(), "-y", "-nostdin",
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:v", "libx264", "-crf", "16", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-an",
        output_path
    ]

    result = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=600
    )
    if result.returncode != 0:
        raise Exception("FFmpeg pad failed (code %d): %s" % (result.returncode, result.stderr[-500:]))

    return pad_frames


# ---------------------------------------------------------------------------
# Smart auto-trim: reference frames + difference matte
# ---------------------------------------------------------------------------

def extract_frame_as_png(input_path, output_path, frame_num=0):
    """Extract a single frame as PNG at native resolution.

    Args:
        input_path: Path to the video file.
        output_path: Path to save the PNG.
        frame_num: 0-indexed frame number to extract.
    """
    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg, "-y", "-nostdin",
        "-i", input_path,
        "-vf", "select=eq(n\\,%d)" % frame_num,
        "-frames:v", "1",
        "-update", "1",
        output_path
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def extract_reference_frames(input_path, output_dir, _log=None):
    """Extract first and last frame as PNGs for diff-matte comparison.

    Returns (head_ref_path, tail_ref_path).
    """
    head_ref = os.path.join(output_dir, "_ref_head.png")
    tail_ref = os.path.join(output_dir, "_ref_tail.png")

    ffmpeg = get_ffmpeg_path()

    # First frame
    cmd_head = [
        ffmpeg, "-y", "-nostdin",
        "-i", input_path,
        "-vf", "select=eq(n\\,0),scale=480:270:force_original_aspect_ratio=disable",
        "-frames:v", "1",
        head_ref
    ]
    subprocess.run(cmd_head, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)

    # Last frame
    cmd_tail = [
        ffmpeg, "-y", "-nostdin",
        "-sseof", "-0.2",
        "-i", input_path,
        "-vf", "scale=480:270:force_original_aspect_ratio=disable",
        "-frames:v", "1",
        tail_ref
    ]
    subprocess.run(cmd_tail, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)

    if _log:
        _log("  Saved reference frames for auto-trim")
    return head_ref, tail_ref


def compute_consecutive_diff(video_path, frame_a, frame_b):
    """Compute difference score between two frames of the SAME video.

    Uses -ss seek for fast access. Both frames scaled to 480x270.
    Returns an integer 0 (identical) to 100 (completely different).
    Lower = more similar (likely duplicate).
    """
    ffmpeg = get_ffmpeg_path()
    _, _, _, v_fps, _, _ = probe_video(video_path)

    seek_a = frame_a / float(v_fps) if v_fps > 0 else 0
    seek_b = frame_b / float(v_fps) if v_fps > 0 else 0

    # Extract both frames as PNGs, diff them
    import tempfile
    tmp_a = os.path.join(tempfile.gettempdir(), "_diff_a.png")
    tmp_b = os.path.join(tempfile.gettempdir(), "_diff_b.png")

    for seek, tmp in [(seek_a, tmp_a), (seek_b, tmp_b)]:
        cmd = [
            ffmpeg, "-y", "-nostdin",
            "-ss", str(seek),
            "-i", video_path,
            "-vf", "scale=480:270:force_original_aspect_ratio=disable",
            "-frames:v", "1",
            tmp
        ]
        subprocess.run(cmd, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)

    # Now diff the two PNGs
    cmd = [
        ffmpeg, "-nostdin",
        "-i", tmp_a,
        "-i", tmp_b,
        "-filter_complex",
        "[0:v][1:v]blend=all_mode=difference,blackframe=amount=0:threshold=32",
        "-frames:v", "1",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, timeout=30)

    # Cleanup
    for tmp in [tmp_a, tmp_b]:
        try:
            os.remove(tmp)
        except OSError:
            pass

    # Parse pblack
    pblack = 0
    for line in result.stderr.split("\n"):
        if "pblack:" in line:
            try:
                pblack = int(line.split("pblack:")[1].strip().split()[0])
            except (ValueError, IndexError):
                pass

    # 0 = identical (pblack=100), 100 = different (pblack=0)
    return 100 - pblack


def auto_trim_output(output_path, expected_frames, head_ref, tail_ref,
                     fps, safety_pad=0, fps_multiplier=1, _log=None):
    """Analyze Topaz output and trim duplicate safety-pad frames.

    Strategy: instead of comparing against the original source (which Topaz
    transforms too heavily), detect DUPLICATE FRAMES within the output.
    Safety pad frames are copies of the first/last real frame, so consecutive
    frame diffs at the head/tail will show near-zero difference for duplicates
    and normal motion difference for real content transitions.

    Returns the (possibly trimmed) output path and the final frame count.
    """
    def _l(msg):
        if _log:
            _log(msg)

    _, _, actual_frames, out_fps, _, _ = probe_video(output_path)

    # Adjust expected for interpolation multiplier
    if fps_multiplier > 1:
        expected_with_pad = (expected_frames + 2 * safety_pad) * fps_multiplier
        expected_no_pad = expected_frames * fps_multiplier
    else:
        expected_with_pad = expected_frames + 2 * safety_pad
        expected_no_pad = expected_frames

    _l("")
    _l("  === AUTO-TRIM ANALYSIS ===")
    _l("  Expected frames (no pad): %d" % expected_no_pad)
    if safety_pad > 0:
        _l("  Expected frames (with pad): %d" % expected_with_pad)
    _l("  Actual output frames: %d" % actual_frames)

    trim_fps = out_fps if out_fps > 0 else fps

    # Case 1: Perfect match -- no extras to trim
    if actual_frames == expected_no_pad:
        _l("  Result: PERFECT MATCH -- no trim needed")
        _l("  ===========================")
        return output_path, actual_frames

    # Case 2: Topaz lost frames -- don't trim, warn
    if actual_frames < expected_no_pad:
        _l("  Result: WARNING -- Topaz returned FEWER frames than expected")
        _l("  Deficit: %d frames lost" % (expected_no_pad - actual_frames))
        _l("  No trimming applied (would make it worse)")
        _l("  ===========================")
        return output_path, actual_frames

    # Case 3+4: Extra frames -- scan for duplicates at head and tail
    excess = actual_frames - expected_no_pad
    _l("  Extra frames: %d -- scanning for duplicates..." % excess)

    # Scan head: compare consecutive frames to find where duplicates end
    scan_range = min(excess + 3, 8)
    _l("  Scanning head (consecutive diffs, frames 0-%d)..." % scan_range)
    head_dupes = 0
    for i in range(scan_range):
        score = compute_consecutive_diff(output_path, i, i + 1)
        is_dupe = score < 15  # threshold: < 15 = likely duplicate
        _l("    Frame %d vs %d: diff = %d %s" % (i, i + 1, score,
            "<-- DUPLICATE" if is_dupe else ""))
        if is_dupe:
            head_dupes += 1
        else:
            break  # first real motion = end of duplicate run

    # Scan tail: compare consecutive frames from the end
    _l("  Scanning tail (consecutive diffs, last %d frames)..." % scan_range)
    tail_dupes = 0
    for i in range(scan_range):
        idx = actual_frames - 1 - i
        score = compute_consecutive_diff(output_path, idx, idx - 1)
        is_dupe = score < 15
        _l("    Frame %d vs %d: diff = %d %s" % (idx, idx - 1, score,
            "<-- DUPLICATE" if is_dupe else ""))
        if is_dupe:
            tail_dupes += 1
        else:
            break

    _l("  Detected: %d duplicate(s) at head, %d at tail" % (head_dupes, tail_dupes))

    # CRITICAL: never trim more than the safety pad count per end.
    # On static/slow shots, real frames also have near-zero consecutive diffs.
    max_trim = safety_pad * (fps_multiplier if fps_multiplier > 1 else 1)
    if head_dupes > max_trim:
        _l("  Capping head trim to %d (safety pad limit)" % max_trim)
        head_dupes = max_trim
    if tail_dupes > max_trim:
        _l("  Capping tail trim to %d (safety pad limit)" % max_trim)
        tail_dupes = max_trim

    # ALSO: total trim must not exceed total excess frames.
    # If Topaz already ate some safety frames, we have fewer to trim.
    total_trim = head_dupes + tail_dupes
    if total_trim > excess:
        _l("  Total trim (%d) exceeds excess (%d) -- reducing..." % (total_trim, excess))
        # Distribute excess evenly, prefer trimming the end with lower diff (more likely dupe)
        if excess == 0:
            head_dupes = 0
            tail_dupes = 0
        elif excess == 1:
            # Trim from the end with more confidence (we don't know which one Topaz ate)
            # Keep 1 from whichever end, zero the other
            head_dupes = 1
            tail_dupes = 0
        else:
            # Distribute evenly
            head_dupes = excess // 2
            tail_dupes = excess - head_dupes
        _l("  Adjusted trim: %d head, %d tail" % (head_dupes, tail_dupes))

    if head_dupes == 0 and tail_dupes == 0:
        _l("  No trimming needed")
        _l("  ===========================")
        return output_path, actual_frames

    _l("  Trimming: %d from head, %d from tail" % (head_dupes, tail_dupes))
    trimmed_path = _trim_head_tail(
        output_path, trim_fps,
        head_frames=head_dupes,
        tail_frames=tail_dupes,
        _log=_log
    )
    _, _, final_frames, _, _, _ = probe_video(trimmed_path)
    _l("  Trimmed: %d -> %d frames (expected %d)" % (actual_frames, final_frames, expected_no_pad))
    if final_frames > expected_no_pad:
        _l("  Note: result is %d frames longer than expected -- OK for editorial" % (
            final_frames - expected_no_pad))
    elif final_frames < expected_no_pad:
        _l("  Note: result is %d frames shorter than expected" % (
            expected_no_pad - final_frames))
    _l("  ===========================")
    return trimmed_path, final_frames


def _trim_head_tail(input_path, fps, head_frames, tail_frames, _log=None):
    """Trim head_frames from the start and tail_frames from the end."""
    _, _, total_frames, _, _, _ = probe_video(input_path)

    start_sec = head_frames / float(fps)
    end_frame = total_frames - tail_frames
    duration_sec = (end_frame - head_frames) / float(fps)

    base, ext = os.path.splitext(input_path)
    trimmed_path = base + "_trimmed" + ext

    # Determine codec from extension
    if ext.lower() == ".mov":
        codec_args = ["-c:v", "prores_ks", "-profile:v", "3"]
    else:
        codec_args = ["-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p"]

    cmd = [
        get_ffmpeg_path(), "-y", "-nostdin",
        "-ss", str(start_sec),
        "-i", input_path,
        "-t", str(duration_sec),
    ] + codec_args + [
        "-an",
        trimmed_path
    ]

    result = subprocess.run(
        cmd, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, timeout=600
    )
    if result.returncode != 0:
        if _log:
            _log("  WARNING: trim failed, keeping original: %s" % result.stderr[-200:])
        return input_path

    # Replace original with trimmed version
    try:
        os.remove(input_path)
        os.rename(trimmed_path, input_path)
    except OSError:
        return trimmed_path

    return input_path


# ---------------------------------------------------------------------------
# Shared API helpers (used by both upscale and interpolation)
# ---------------------------------------------------------------------------

def _upload_with_retry(url, filepath, content_type, _log, max_retries=3):
    """Upload a file with exponential backoff retry."""
    file_mb = os.path.getsize(filepath) / 1048576.0
    for attempt in range(max_retries):
        try:
            _log("  Uploading %.1f MB%s..." % (
                file_mb, " (retry %d)" % attempt if attempt > 0 else ""))
            with open(filepath, "rb") as f:
                resp = requests.put(url, data=f, headers={"Content-Type": content_type})
            if resp.status_code in (200, 201):
                _log("  Upload complete. Processing...")
                return resp
            _log("  Upload returned %d, retrying..." % resp.status_code)
        except requests.exceptions.RequestException as e:
            _log("  Upload error: %s" % str(e))
            if attempt == max_retries - 1:
                raise
        time.sleep(2 ** attempt)  # 1s, 2s, 4s
    raise Exception("Upload failed after %d attempts" % max_retries)


def _poll_for_completion(request_id, api_key, _log, task_label="Processing"):
    """Poll Topaz API until job completes. Returns download URL."""
    status_url = "https://api.topazlabs.com/video/%s/status" % request_id
    poll_count = 0
    last_progress = -1
    last_progress_poll = 0
    stall_limit_seconds = 600  # 10 minutes with no progress change = stalled

    while True:
        time.sleep(5)
        poll_count += 1
        try:
            s_resp = requests.get(status_url, headers={"X-API-Key": api_key})
        except requests.exceptions.RequestException:
            continue
        if s_resp.status_code == 200:
            s_data = s_resp.json()
            status = s_data.get("status")
            progress = s_data.get("progress", 0)
            estimates = s_data.get("estimates", {})
            time_est = estimates.get("time", [])

            # Log progress updates (only when progress changes)
            if progress != last_progress:
                last_progress = progress
                last_progress_poll = poll_count
                elapsed_min = (poll_count * 5) / 60.0
                msg = "  %s: %d%%" % (task_label, progress)
                if time_est and len(time_est) >= 2:
                    remaining_sec = time_est[1] - (poll_count * 5)
                    if remaining_sec > 60:
                        msg += " (est. %.0f min remaining)" % (remaining_sec / 60.0)
                    elif remaining_sec > 0:
                        msg += " (est. %d sec remaining)" % remaining_sec
                msg += " [%.1f min elapsed]" % elapsed_min
                _log(msg)

            if status == "complete":
                download_url = s_data.get("download", {}).get("url")
                elapsed_min = (poll_count * 5) / 60.0
                _log("  %s complete! [%.1f min total]" % (task_label, elapsed_min))
                # Log credit/cost info if available
                credits_used = s_data.get("credits", s_data.get("cost", s_data.get("creditsUsed")))
                if credits_used is not None:
                    _log("  Credits consumed: %s" % credits_used)
                # Log full response for debugging (helps discover new fields)
                _log("  Completion response keys: %s" % list(s_data.keys()))
                return download_url, s_data
            elif status in ("failed", "canceled"):
                error_msg = s_data.get("error", s_data.get("message", ""))
                raise Exception("Topaz processing %s: %s\nFull response: %s" % (
                    status, error_msg, json.dumps(s_data, indent=2)))

            # Stall detection: seconds since last progress change
            stall_seconds = (poll_count - last_progress_poll) * 5
            if stall_seconds >= stall_limit_seconds:
                raise Exception(
                    "Stalled: no progress for %d minutes (stuck at %d%%). "
                    "Request ID: %s" % (stall_limit_seconds // 60, last_progress, request_id)
                )


def _download_result(download_url, output_path, _log):
    """Download the processed video from Topaz. Verifies HTTP status."""
    if not download_url:
        raise Exception("No download URL returned")
    _log("  Downloading result...")
    d_resp = requests.get(download_url, stream=True)
    if d_resp.status_code != 200:
        raise Exception("Download failed with HTTP %d" % d_resp.status_code)
    downloaded = 0
    with open(output_path, "wb") as f:
        for chunk in d_resp.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
    dl_mb = downloaded / 1048576.0
    _log("  Downloaded: %.1f MB" % dl_mb)


def _upload_mask_asset(mask_path, api_key, _log):
    """Upload a mask PNG and return a public URL for mask_uri.

    Tries multiple strategies:
    1. Topaz /video/assets endpoint
    2. file.io (free one-time-download hosting)
    3. 0x0.st (free file hosting)
    """

    # Strategy 1: Try the Topaz /video/assets upload endpoint
    try:
        _log("  Trying Topaz asset upload endpoint...")
        headers = {
            "X-API-Key": api_key,
            "accept": "application/json",
            "content-type": "application/json"
        }
        mask_size = os.path.getsize(mask_path)
        asset_payload = {
            "type": "mask",
            "contentType": "image/png",
            "size": mask_size
        }
        resp = requests.post("https://api.topazlabs.com/video/assets",
                           headers=headers, json=asset_payload)
        if resp.status_code == 200:
            asset_data = resp.json()
            _log("  Asset endpoint response: %s" % json.dumps(asset_data, indent=2))
            upload_url = asset_data.get("uploadUrl") or asset_data.get("url")
            asset_uri = asset_data.get("uri") or asset_data.get("assetUri")
            if upload_url:
                _upload_with_retry(upload_url, mask_path, "image/png", _log)
                _log("  Mask uploaded via Topaz asset endpoint.")
                return asset_uri or upload_url
        else:
            _log("  Topaz asset endpoint returned %d" % resp.status_code)
    except Exception as e:
        _log("  Topaz asset endpoint failed: %s" % str(e))

    # Strategy 2: Upload to litterbox.catbox.moe (temporary, 1 hour)
    try:
        _log("  Uploading mask to litterbox (temp 1h hosting)...")
        with open(mask_path, "rb") as f:
            resp = requests.post(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data={"reqtype": "fileupload", "time": "1h"},
                files={"fileToUpload": (os.path.basename(mask_path), f, "image/png")},
                timeout=30
            )
        if resp.status_code == 200 and resp.text.strip().startswith("http"):
            mask_url = resp.text.strip()
            _log("  Mask hosted at: %s" % mask_url)
            return mask_url
        _log("  litterbox returned %d: %s" % (resp.status_code, resp.text[:100]))
    except Exception as e:
        _log("  litterbox failed: %s" % str(e))

    # Strategy 3: Upload to catbox.moe (permanent)
    try:
        _log("  Uploading mask to catbox.moe...")
        with open(mask_path, "rb") as f:
            resp = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": (os.path.basename(mask_path), f, "image/png")},
                timeout=30
            )
        if resp.status_code == 200 and resp.text.strip().startswith("http"):
            mask_url = resp.text.strip()
            _log("  Mask hosted at: %s" % mask_url)
            return mask_url
        _log("  catbox returned %d: %s" % (resp.status_code, resp.text[:100]))
    except Exception as e:
        _log("  catbox failed: %s" % str(e))

    _log("  *** ERROR: Could not upload mask to any hosting service.")
    return None


def _create_api_request(payload, api_key, _log):
    """Submit a job to Topaz API. Returns (request_id, upload_url, all_upload_urls)."""
    headers = {
        "X-API-Key": api_key,
        "accept": "application/json",
        "content-type": "application/json"
    }
    _log("  Creating Topaz API request...")
    _log("  API Payload: %s" % json.dumps(payload, indent=2))
    resp = requests.post("https://api.topazlabs.com/video/express", headers=headers, json=payload)
    _log("  API Response: %d" % resp.status_code)
    if resp.status_code != 200:
        _log("  API Error Body: %s" % resp.text[:500])
        raise Exception("Topaz API error %d: %s" % (resp.status_code, resp.text[:200]))

    req_data = resp.json()
    request_id = req_data["requestId"]
    upload_urls = req_data["uploadUrls"]
    upload_url = upload_urls[0]
    _log("  Request ID: %s" % request_id)
    if len(upload_urls) > 1:
        _log("  Upload URLs: %d (source + mask)" % len(upload_urls))
    _log("  API Response Body: %s" % json.dumps(req_data, indent=2))
    # Log estimated credit cost
    estimates = req_data.get("estimates", {})
    cost_est = estimates.get("cost")
    if cost_est and len(cost_est) >= 2:
        _log("  Estimated cost: %d-%d credits" % (cost_est[0], cost_est[1]))
    return request_id, upload_url, upload_urls


def _determine_codec(input_path):
    """Determine source container and output encoder/container from file extension."""
    ext = os.path.splitext(input_path)[1].lower().lstrip(".")
    if ext in ("mp4", "mov", "mkv", "avi", "webm"):
        src_container = ext
    else:
        src_container = "mp4"
    if src_container == "mov":
        return src_container, "ProRes", "mov"
    else:
        return src_container, "h265", "mp4"


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------

def process_topaz_video(input_path, output_path, api_key, model_code, out_w=None, out_h=None,
                        container="mov", filter_params=None, mask_path=None, progress_callback=None):
    """Submit to Topaz API, upload, poll, download. Returns request ID.

    Args:
        mask_path: Optional path to a mask PNG for object removal (remove-1).
        progress_callback: Optional function(msg) called with status updates during polling.
    """
    if filter_params is None:
        filter_params = {}

    def _log(msg):
        if progress_callback:
            progress_callback(msg)

    width, height, nb_frames, fps, duration, file_size = probe_video(input_path)

    # Default to 2x if no output resolution specified
    if out_w is None:
        out_w = width * 2
    if out_h is None:
        out_h = height * 2

    src_container, out_encoder, out_container = _determine_codec(input_path)

    # Build filter object with model-specific parameters
    upscale_filter = {
        "model": model_code,
        "videoType": "Progressive"
    }

    auto_mode = filter_params.get("auto_mode", "Auto")
    if auto_mode != "Auto":
        upscale_filter["auto"] = auto_mode
        # Include manual/relative tuning parameters
        for key in ("compression", "details", "noise", "blur", "halo",
                     "recoverOriginalDetailValue", "grain"):
            if key in filter_params:
                upscale_filter[key] = filter_params[key]

    # Creativity for generative models (slc, hyp, wonder, etc.)
    creativity = filter_params.get("creativity")
    if creativity:
        upscale_filter["creativity"] = creativity

    # Prompt for generative/removal models
    prompt = filter_params.get("prompt")
    if prompt:
        upscale_filter["prompt"] = prompt

    # Mask for object removal models -- must upload mask first to get URI
    if mask_path:
        mask_size = os.path.getsize(mask_path)
        _log("  Mask file: %s (%d bytes)" % (mask_path, mask_size))
        # Upload mask to Topaz's asset storage to get a mask_uri
        mask_uri = _upload_mask_asset(mask_path, api_key, _log)
        if mask_uri:
            upscale_filter["mask_uri"] = mask_uri
            _log("  mask_uri: %s" % mask_uri[:100])
        else:
            _log("  *** WARNING: Could not obtain mask_uri. API may reject request.")

    payload = {
        "source": {
            "container": src_container,
            "frameCount": nb_frames,
            "frameRate": fps,
            "duration": duration,
            "size": file_size,
            "resolution": {"width": width, "height": height}
        },
        "filters": [upscale_filter],
        "output": {
            "resolution": {"width": out_w, "height": out_h},
            "frameRate": fps,
            "videoEncoder": out_encoder,
            "container": out_container,
            "audioTransfer": "Copy",
            "audioCodec": "AAC"
        }
    }

    # 1. Create request
    request_id, upload_url, all_upload_urls = _create_api_request(payload, api_key, _log)

    # 2. Upload video with retry
    _upload_with_retry(upload_url, input_path, "video/%s" % src_container, _log)

    # 4. Poll for completion
    download_url, completion_data = _poll_for_completion(request_id, api_key, _log, task_label="Processing")

    # 5. Download with verification
    _download_result(download_url, output_path, _log)

    return request_id


def process_topaz_interpolation(input_path, output_path, api_key, model_code,
                                 fps_multiplier=2, slowmo=1,
                                 interpolate_dupes=True, dupe_threshold=0.01,
                                 progress_callback=None):
    """Submit a frame-interpolation job (Chronos / Apollo) to Topaz API.

    Args:
        fps_multiplier: Integer multiplier for output FPS (1 = same rate, 2 = double, etc.)
        slowmo: Slow-motion factor (1 = normal speed, 2 = half speed / double duration)
        interpolate_dupes: Detect and replace duplicate frames with AI-interpolated ones.
        dupe_threshold: Sensitivity for duplicate detection (lower = more sensitive).
        progress_callback: Optional function(msg) called with status updates.
    """
    def _log(msg):
        if progress_callback:
            progress_callback(msg)

    width, height, nb_frames, fps, duration, file_size = probe_video(input_path)

    output_fps = fps * fps_multiplier

    src_container, out_encoder, out_container = _determine_codec(input_path)

    # Build FrameInterpolationFilter (different from UpscaleFilter)
    interp_filter = {
        "model": model_code,
        "fps": output_fps,
        "slowmo": slowmo,
        "duplicate": interpolate_dupes,
        "duplicateThreshold": dupe_threshold,
    }

    payload = {
        "source": {
            "container": src_container,
            "frameCount": nb_frames,
            "frameRate": fps,
            "duration": duration,
            "size": file_size,
            "resolution": {"width": width, "height": height}
        },
        "filters": [interp_filter],
        "output": {
            "resolution": {"width": width, "height": height},
            "frameRate": output_fps,
            "videoEncoder": out_encoder,
            "container": out_container,
            "audioTransfer": "Copy",
            "audioCodec": "AAC"
        }
    }

    _log("  Creating Topaz API interpolation request (%s, %dx FPS, slowmo=%d)..." % (
        model_code, fps_multiplier, slowmo))

    # 1. Create request
    request_id, upload_url, _ = _create_api_request(payload, api_key, _log)

    # 2. Upload with retry
    _upload_with_retry(upload_url, input_path, "video/%s" % src_container, _log)

    # 3. Poll for completion
    download_url, completion_data = _poll_for_completion(request_id, api_key, _log, task_label="Interpolation")

    # 4. Download with verification
    _download_result(download_url, output_path, _log)

    return request_id
