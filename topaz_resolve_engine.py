import sys
import os
import time
import requests
import subprocess
import argparse
import json

CONFIG_FILE = os.path.expanduser("~/.topaz_resolve_config.json")

def get_api_key():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data.get("api_key", "")
        except:
            pass
    return ""

def save_api_key(api_key):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump({"api_key": api_key}, f)
    except Exception as e:
        print(f"Failed to save config: {e}")
import os
import time
import requests
import subprocess
import argparse

def get_resolve_objects():
    # Inject Resolve module path for Mac
    mac_path = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
    if os.path.exists(mac_path) and mac_path not in sys.path:
        sys.path.append(mac_path)
    
    # Attempt to connect to DaVinci Resolve
    try:
        import DaVinciResolveScript as dvr_script
        resolve = dvr_script.scriptapp("Resolve")
        if resolve is None:
            print("Could not connect to DaVinci Resolve. Make sure Resolve is running and External Scripting is enabled.")
            sys.exit(1)
        project_manager = resolve.GetProjectManager()
        project = project_manager.GetCurrentProject()
        timeline = project.GetCurrentTimeline()
        media_pool = project.GetMediaPool()
        return resolve, project, timeline, media_pool
    except ImportError:
        print("DaVinciResolveScript not found. Ensure your PYTHONPATH is set correctly.")
        sys.exit(1)

def get_ffmpeg_path():
    import os
    if os.path.exists("/opt/homebrew/bin/ffmpeg"): return "/opt/homebrew/bin/ffmpeg"
    if os.path.exists("/usr/local/bin/ffmpeg"): return "/usr/local/bin/ffmpeg"
    return "ffmpeg"

def get_ffprobe_path():
    import os
    if os.path.exists("/opt/homebrew/bin/ffprobe"): return "/opt/homebrew/bin/ffprobe"
    if os.path.exists("/usr/local/bin/ffprobe"): return "/usr/local/bin/ffprobe"
    return "ffprobe"

def extract_clip(input_path, output_path, start_frame, end_frame, fps, handles, log_cb=None):
    """Uses ffmpeg to extract the portion of the clip with handles."""
    if log_cb is None:
        log_cb = lambda x: None
        
    # Convert frames to seconds for ffmpeg
    start_sec = max(0, (start_frame - handles) / float(fps))
    duration_sec = ((end_frame - start_frame) + (handles * 2)) / float(fps)
    
    cmd = [
        get_ffmpeg_path(), "-y", "-nostdin",
        "-ss", str(start_sec),
        "-i", input_path,
        "-t", str(duration_sec),
        "-c:v", "prores_ks", "-profile:v", "3", # ProRes HQ
        "-c:a", "copy",
        output_path
    ]
    
    log_cb(f"FFmpeg Command:\n{' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFmpeg failed with code {e.returncode}.\nStderr:\n{e.stderr}")
    except subprocess.TimeoutExpired as e:
        raise Exception(f"FFmpeg timed out after 300 seconds.\nStderr:\n{e.stderr}")

def process_topaz_video(input_path, output_path, api_key, model_code, scale=1.0, container="mov", log_cb=None):
    """Submits the extracted clip to Topaz API and downloads the result."""
    if log_cb is None:
        log_cb = lambda x: None
        
    file_size = os.path.getsize(input_path)
    
    # Simple ffprobe to get frames and fps
    probe_cmd = [get_ffprobe_path(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames,r_frame_rate,width,height", "-of", "json", input_path]
    import json
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    probe_data = json.loads(probe_result.stdout)
    stream = probe_data['streams'][0]
    
    width = int(stream['width'])
    height = int(stream['height'])
    try:
        nb_frames = int(stream['nb_frames'])
    except:
        nb_frames = 100 # Fallback if nb_frames is missing
        
    fps_str = stream['r_frame_rate'].split('/')
    fps = float(fps_str[0]) / float(fps_str[1])
    duration = nb_frames / fps

    payload = {
        "source": {
            "container": container,
            "frameCount": nb_frames,
            "frameRate": fps,
            "duration": duration,
            "size": file_size,
            "resolution": {"width": width, "height": height}
        },
        "filters": [{"model": model_code, "videoType": "Progressive"}],
        "output": {
            "resolution": {"width": int(width * scale), "height": int(height * scale)},
            "frameRate": fps,
            "videoEncoder": "ProRes",
            "container": container,
            "audioTransfer": "Copy"
        }
    }

    headers = {"X-API-Key": api_key, "accept": "application/json", "content-type": "application/json"}

    log_cb(f"Submitting request for {model_code}...")
    resp = requests.post("https://api.topazlabs.com/video/express", headers=headers, json=payload)
    if resp.status_code != 200:
        raise Exception(f"Failed to create Topaz request: {resp.status_code} {resp.text}")
    
    req_data = resp.json()
    request_id = req_data["requestId"]
    upload_url = req_data["uploadUrls"][0]

    log_cb("Uploading video to Topaz Cloud...")
    with open(input_path, "rb") as f:
        upload_resp = requests.put(upload_url, data=f, headers={"Content-Type": f"video/{container}"})
        if upload_resp.status_code not in (200, 201):
            raise Exception("Upload failed.")

    log_cb(f"Request ID: {request_id}. Processing...")
    status_url = f"https://api.topazlabs.com/video/{request_id}/status"
    download_url = None
    last_prog = -1
    while True:
        time.sleep(5)
        s_resp = requests.get(status_url, headers={"X-API-Key": api_key})
        if s_resp.status_code == 200:
            s_data = s_resp.json()
            status = s_data.get("status")
            progress = s_data.get("progress", 0)
            
            if status == "processing":
                if progress != last_prog:
                    log_cb(f"Topaz Status: Processing | {progress:.0f}%")
                    last_prog = progress
            elif status == "complete":
                log_cb("Topaz Status: Complete!")
                download_url = s_data.get("download", {}).get("url")
                break
            elif status in ("failed", "canceled"):
                raise Exception(f"Processing {status}")

    log_cb("Downloading enhanced video...")
    d_resp = requests.get(download_url, stream=True)
    with open(output_path, "wb") as f:
        for chunk in d_resp.iter_content(chunk_size=65536):
            f.write(chunk)
    log_cb("Download complete.")

def main():
    parser = argparse.ArgumentParser(description="Process Resolve Clip with Topaz API")
    parser.add_argument("--model", type=str, required=True, help="Topaz Model Code (e.g. prob-4)")
    parser.add_argument("--scale", type=float, default=1.0, help="Scale factor (e.g. 2.0)")
    parser.add_argument("--handles", type=int, default=0, help="Frames to add as handles")
    parser.add_argument("--api_key", type=str, default="", help="Topaz API Key")
    args = parser.parse_args()

    # Load API key from args or config
    final_api_key = args.api_key if args.api_key else get_api_key()
    
    if not final_api_key or final_api_key == "YOUR_TOPAZ_API_KEY":
        print("Error: No Topaz API key provided. Please run the Batch Script UI first to save your key.")
        sys.exit(1)

    resolve, project, timeline, media_pool = get_resolve_objects()

    if not timeline:
        print("No active timeline found.")
        sys.exit(1)

    # For a Fusion Macro dropping on a clip, the most robust way to find the clip 
    # is to get the current video item at the playhead
    current_timecode = timeline.GetCurrentTimecode()
    # Resolve API doesn't easily convert timecode to frames without knowing frame rate,
    # but we can get the currently selected clip.
    selected_items = timeline.GetItemListInTrack("video", 1) # Simplification: need to find exact item
    
    # A better approach: require the user to SELECT the clip they want to process
    current_item = timeline.GetCurrentVideoItem()
    if not current_item:
        print("Please ensure your playhead is over the clip you want to process, or select it.")
        sys.exit(1)

    media_pool_item = current_item.GetMediaPoolItem()
    if not media_pool_item:
        print("Could not find media pool item for the clip.")
        sys.exit(1)

    clip_path = media_pool_item.GetClipProperty("File Path")
    clip_fps = float(media_pool_item.GetClipProperty("FPS"))
    
    start_frame = current_item.GetStart()
    end_frame = current_item.GetEnd()

    # Extract path info
    base_dir = os.path.dirname(clip_path)
    base_name = os.path.splitext(os.path.basename(clip_path))[0]
    
    extracted_path = os.path.join(base_dir, f"{base_name}_extracted.mov")
    topaz_output_path = os.path.join(base_dir, f"{base_name}_{args.model}.mov")

    print(f"Extracting: {clip_path}")
    extract_clip(clip_path, extracted_path, start_frame, end_frame, clip_fps, args.handles)

    print(f"Processing with Topaz ({args.model})...")
    # For command line testing, defaulting to args.scale
    process_topaz_video(extracted_path, topaz_output_path, final_api_key, args.model, scale=args.scale)

    print(f"Importing {topaz_output_path} to Media Pool...")
    # Import into the currently active bin
    media_pool.ImportMedia([topaz_output_path])

    # Cleanup temporary extraction
    if os.path.exists(extracted_path):
        os.remove(extracted_path)

    print("Success!")

if __name__ == "__main__":
    main()
