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
                return download_url
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


def _create_api_request(payload, api_key, _log):
    """Submit a job to Topaz API. Returns (request_id, upload_url)."""
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
    upload_url = req_data["uploadUrls"][0]
    _log("  Request ID: %s" % request_id)
    _log("  API Response Body: %s" % json.dumps(req_data, indent=2))
    return request_id, upload_url


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

def process_topaz_video(input_path, output_path, api_key, model_code, out_w=None, out_h=None, container="mov", filter_params=None, progress_callback=None):
    """Submit to Topaz API, upload, poll, download. Returns request ID.

    Args:
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
    request_id, upload_url = _create_api_request(payload, api_key, _log)

    # 2. Upload with retry
    _upload_with_retry(upload_url, input_path, "video/%s" % src_container, _log)

    # 3. Poll for completion
    download_url = _poll_for_completion(request_id, api_key, _log, task_label="Processing")

    # 4. Download with verification
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
    request_id, upload_url = _create_api_request(payload, api_key, _log)

    # 2. Upload with retry
    _upload_with_retry(upload_url, input_path, "video/%s" % src_container, _log)

    # 3. Poll for completion
    download_url = _poll_for_completion(request_id, api_key, _log, task_label="Interpolation")

    # 4. Download with verification
    _download_result(download_url, output_path, _log)

    return request_id
