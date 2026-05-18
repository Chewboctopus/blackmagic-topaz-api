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
            with open(CONFIG_FILE, "r") as f:
                return json.load(f).get("api_key", "")
        except Exception:
            pass
    return ""

def save_api_key(api_key):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump({"api_key": api_key}, f)
    except Exception:
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
        nb_frames = 100

    fps_parts = stream['r_frame_rate'].split('/')
    fps = float(fps_parts[0]) / float(fps_parts[1])
    duration = nb_frames / fps
    file_size = os.path.getsize(input_path)

    return width, height, nb_frames, fps, duration, file_size

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

def process_topaz_video(input_path, output_path, api_key, model_code, out_w=None, out_h=None, container="mov", filter_params=None):
    """Submit to Topaz API, upload, poll, download. Returns request ID."""
    if filter_params is None:
        filter_params = {}

    width, height, nb_frames, fps, duration, file_size = probe_video(input_path)

    # Default to 2x if no output resolution specified
    if out_w is None:
        out_w = width * 2
    if out_h is None:
        out_h = height * 2

    # Determine input container from file extension
    ext = os.path.splitext(input_path)[1].lower().lstrip(".")
    if ext in ("mp4", "mov", "mkv", "avi", "webm"):
        src_container = ext
    else:
        src_container = "mp4"
    # Match output encoding to source format
    if src_container == "mov":
        out_encoder = "ProRes"
        out_container = "mov"
    else:
        # MP4, MKV, WebM etc — use H265 in MP4
        out_encoder = "h265"
        out_container = "mp4"

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
            "audioTransfer": "Copy"
        }
    }

    headers = {
        "X-API-Key": api_key,
        "accept": "application/json",
        "content-type": "application/json"
    }

    # 1. Create request
    resp = requests.post("https://api.topazlabs.com/video/express", headers=headers, json=payload)
    if resp.status_code != 200:
        raise Exception("Topaz API error %d: %s" % (resp.status_code, resp.text[:200]))

    req_data = resp.json()
    request_id = req_data["requestId"]
    upload_url = req_data["uploadUrls"][0]

    # 2. Upload
    with open(input_path, "rb") as f:
        upload_resp = requests.put(upload_url, data=f, headers={"Content-Type": "video/%s" % src_container})
        if upload_resp.status_code not in (200, 201):
            raise Exception("Upload failed: %d" % upload_resp.status_code)

    # 3. Poll for completion
    status_url = "https://api.topazlabs.com/video/%s/status" % request_id
    while True:
        time.sleep(5)
        try:
            s_resp = requests.get(status_url, headers={"X-API-Key": api_key})
        except Exception:
            continue
        if s_resp.status_code == 200:
            s_data = s_resp.json()
            status = s_data.get("status")
            if status == "complete":
                download_url = s_data.get("download", {}).get("url")
                break
            elif status in ("failed", "canceled"):
                # Capture full error details
                error_msg = s_data.get("error", s_data.get("message", ""))
                raise Exception("Topaz processing %s: %s\nFull response: %s" % (
                    status, error_msg, json.dumps(s_data, indent=2)))

    # 4. Download
    if not download_url:
        raise Exception("No download URL returned")
    d_resp = requests.get(download_url, stream=True)
    with open(output_path, "wb") as f:
        for chunk in d_resp.iter_content(chunk_size=65536):
            f.write(chunk)

    return request_id
