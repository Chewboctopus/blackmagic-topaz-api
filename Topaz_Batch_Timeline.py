import sys
import os

# ---------------------------------------------------------------------------
# Import engine
# ---------------------------------------------------------------------------
try:
    import importlib
    _lib_dir = os.path.expanduser(
        "~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/topaz_lib"
    )
    if _lib_dir not in sys.path:
        sys.path.insert(0, _lib_dir)
    import _topaz_resolve_engine as engine
    importlib.reload(engine)
except Exception as e:
    print("Engine import failed: %s" % e)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Resolve objects
# ---------------------------------------------------------------------------
try:
    projectManager = resolve.GetProjectManager()
    project = projectManager.GetCurrentProject()
    timeline = project.GetCurrentTimeline()
    media_pool = project.GetMediaPool()
    fusion = resolve.Fusion()
    ui = fusion.UIManager
    dispatcher = bmd.UIDispatcher(ui)
except NameError:
    print("Must run from DaVinci Resolve Scripts menu.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------
win = dispatcher.AddWindow({
    'ID': "TopazBatchWin",
    'WindowTitle': "Topaz API Batch Processor",
    'Geometry': [200, 100, 560, 780],
}, ui.VGroup([
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Select Video Track:', 'Weight': 0.3}),
        ui.LineEdit({'ID': 'TrackNum', 'Text': '1', 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Topaz Model:', 'Weight': 0.3}),
        ui.ComboBox({'ID': 'ModelCombo', 'Weight': 0.7})
    ]),
    ui.TextEdit({'ID': 'ModelInfo', 'ReadOnly': True, 'Weight': 0, 'FixedSize': [0, 60], 'Font': ui.Font({'PixelSize': 11})}),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Output Resolution:', 'Weight': 0.3}),
        ui.ComboBox({'ID': 'ResCombo', 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Handles (Frames):', 'Weight': 0.3}),
        ui.LineEdit({'ID': 'Handles', 'Text': '0', 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Topaz API Key:', 'Weight': 0.3}),
        ui.LineEdit({'ID': 'APIKey', 'Text': engine.get_api_key() or 'YOUR_API_KEY', 'Weight': 0.7})
    ]),

    # --- Filter Parameters ---
    ui.Label({'Text': '── Filter Parameters ──', 'Weight': 0}),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Mode:', 'Weight': 0.3}),
        ui.ComboBox({'ID': 'AutoMode', 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Creativity:', 'Weight': 0.3}),
        ui.ComboBox({'ID': 'Creativity', 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Compression (-1 to 1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'Compression', 'Value': 0, 'Minimum': -100, 'Maximum': 100, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Details (-1 to 1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'Details', 'Value': 0, 'Minimum': -100, 'Maximum': 100, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Noise (-1 to 1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'Noise', 'Value': 0, 'Minimum': -100, 'Maximum': 100, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Blur/Sharpen (-1 to 1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'Blur', 'Value': 0, 'Minimum': -100, 'Maximum': 100, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Halo (-1 to 1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'Halo', 'Value': 0, 'Minimum': -100, 'Maximum': 100, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Recover Original (0-1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'RecoverDetail', 'Value': 0, 'Minimum': 0, 'Maximum': 100, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Grain Amount (0-0.1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'Grain', 'Value': 0, 'Minimum': 0, 'Maximum': 100, 'Weight': 0.7})
    ]),

    ui.Label({'Text': 'Status:', 'Weight': 0}),
    ui.TextEdit({'ID': 'LogText', 'ReadOnly': True, 'Weight': 1}),
    ui.HGroup({'Weight': 0}, [
        ui.Button({'ID': 'ProcessCurrentBtn', 'Text': 'Process Current Clip', 'Weight': 1}),
        ui.Button({'ID': 'ProcessBatchBtn', 'Text': 'Process Track Batch', 'Weight': 1})
    ])
]))

itm = win.GetItems()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
models = [
    # --- Upscale / Enhancement ---
    "prob-4 (Proteus v4)",
    "pnat-1 (Proteus Natural v1)",
    "ahq-12 (Artemis HQ v12)",
    "alq-13 (Artemis LQ v13)",
    "alqs-2 (Artemis LQ Dehalo v2)",
    "amq-13 (Artemis MQ v13)",
    "amqs-2 (Artemis MQ Dehalo v2)",
    "aaa-9 (Artemis Aliased v9)",
    "aaa-10 (Artemis Aliased v10)",
    "aiob-1 (Artemis IO Balanced v1)",
    "aion-1 (Artemis IO Natural v1)",
    "color-1 (Color v1)",
    "ddv-3 (Dione DV v3)",
    "dtd-4 (Dione TV Detail v4)",
    "dtds-2 (Dione TV Detail Strong v2)",
    "dtv-4 (Dione TV v4)",
    "dtvs-2 (Dione TV Strong v2)",
    "gcg-5 (Gaia CG v5)",
    "ghq-5 (Gaia HQ v5)",
    "ganim-1 (Gaia Anime v1)",
    "hyp-1 (Hyperion v1)",
    "hyp-2 (Hyperion v2)",
    "iris-2 (Iris v2)",
    "iris-3 (Iris v3)",
    "nxf-1 (Nyx Fine v1)",
    "nxl-1 (Nyx Light v1)",
    "nxhf-1 (Nyx HiFi v1)",
    "nyx-3 (Nyx v3)",
    "rhea-1 (Rhea v1)",
    "thd-3 (Theia Detail v3)",
    "thf-4 (Theia Fidelity v4)",
    "thm-2 (Theia Medium v2)",
    "wonder-1 (Wonder v1)",
    # --- Starlight / Astra ---
    "sl-1 (Starlight v1)",
    "slc-1 (Starlight Creative v1)",
    "slf-1 (Starlight Fast v1)",
    "slf-2 (Starlight Fast v2)",
    "slhq-1 (Starlight HQ v1)",
    "slm-1 (Starlight Mini v1)",
    "slp-2 (Starlight Precise v2)",
    "slp-2.5 (Starlight Precise v2.5)",
    # --- Utilities ---
    "stab-1 (Stabilization v1)",
    "remove-1 (Object Removal v1)",
    # --- Frame Interpolation ---
    "apo-8 (Apollo v8)",
    "apf-2 (Apollo Fast v2)",
    "chf-3 (Chronos Fast v3)",
    "chr-2 (Chronos v2)",
]
for m in models:
    itm['ModelCombo'].AddItem(m)

# Model descriptions and parameter support
MODEL_INFO = {
    # --- Proteus ---
    "prob-4": "Proteus v4 — Versatile all-rounder with full manual controls. Best for low-to-medium quality footage. Supports: compression, details, noise, blur, halo, grain.",
    "pnat-1": "Proteus Natural v1 — Natural-looking enhancement, less aggressive than standard Proteus. Good for organic footage.",
    # --- Artemis ---
    "ahq-12": "Artemis HQ v12 — Detail and sharpening for high-quality sources (Blu-ray, ProRes). Preserves existing quality.",
    "alq-13": "Artemis LQ v13 — Restores low-quality, heavily compressed footage. Good for web video, old DVDs.",
    "alqs-2": "Artemis LQ Dehalo v2 — Low-quality restoration with halo removal around edges.",
    "amq-13": "Artemis MQ v13 — Balanced enhancement for medium-quality sources.",
    "amqs-2": "Artemis MQ Dehalo v2 — Medium-quality with halo reduction.",
    "aaa-9": "Artemis Aliased v9 — Removes aliasing/jagged edges from low-res footage.",
    "aaa-10": "Artemis Aliased v10 — Updated anti-aliasing model.",
    "aiob-1": "Artemis IO Balanced v1 — Balanced input/output enhancement.",
    "aion-1": "Artemis IO Natural v1 — Natural-looking IO enhancement.",
    # --- Color ---
    "color-1": "Color v1 — Color correction and enhancement. Improves color accuracy and vibrancy.",
    # --- Dione ---
    "ddv-3": "Dione DV v3 — Specialized for DV/MiniDV camcorder footage deinterlacing and enhancement.",
    "dtd-4": "Dione TV Detail v4 — Deinterlace interlaced TV content with detail preservation.",
    "dtds-2": "Dione TV Detail Strong v2 — Aggressive deinterlacing with strong detail recovery.",
    "dtv-4": "Dione TV v4 — General TV/broadcast deinterlacing.",
    "dtvs-2": "Dione TV Strong v2 — Strong deinterlacing for challenging broadcast footage.",
    # --- Gaia ---
    "gcg-5": "Gaia CG v5 — Optimized for CGI, animation, and anime. Preserves clean lines and flat colors.",
    "ghq-5": "Gaia HQ v5 — Natural upscaling for high-quality footage to 4K/8K. Preserves organic textures.",
    "ganim-1": "Gaia Anime v1 — Specialized for anime content. Clean line work, vibrant colors.",
    # --- Hyperion ---
    "hyp-1": "Hyperion v1 — SDR to HDR conversion. Expands dynamic range and color gamut to HDR10. Supports: creativity.",
    "hyp-2": "Hyperion v2 — Improved SDR to HDR. Better highlight recovery and shadow detail. Supports: creativity.",
    # --- Iris ---
    "iris-2": "Iris v2 — Face recovery and fine detail restoration. Great for portrait-heavy footage.",
    "iris-3": "Iris v3 — Improved face and detail recovery. Best for degraded footage with people.",
    # --- Nyx ---
    "nxf-1": "Nyx Fine v1 — Fine-grained noise reduction. Preserves subtle details while cleaning noise.",
    "nxl-1": "Nyx Light v1 — Light denoising for footage with mild noise.",
    "nxhf-1": "Nyx HiFi v1 — High-fidelity denoising. Maximum detail preservation.",
    "nyx-3": "Nyx v3 — General denoising for low-light, high-ISO, or grainy footage.",
    # --- Rhea ---
    "rhea-1": "Rhea v1 — Stabilization and enhancement model.",
    # --- Theia ---
    "thd-3": "Theia Detail v3 — Maximum detail and sharpness. Best for footage needing extra clarity.",
    "thf-4": "Theia Fidelity v4 — Faithful enhancement preserving original character. Less aggressive than Detail.",
    "thm-2": "Theia Medium v2 — Balanced between Detail and Fidelity.",
    # --- Wonder ---
    "wonder-1": "Wonder v1 — Generative enhancement. Creates new detail using AI generation. Supports: creativity.",
    # --- Starlight ---
    "sl-1": "Starlight v1 — Diffusion-based restoration for severely degraded/archival footage. Rebuilds missing detail.",
    "slc-1": "Starlight Creative v1 — Generative Starlight with creative freedom. Supports: creativity (low/middle/high).",
    "slf-1": "Starlight Fast v1 — Faster diffusion processing, good quality. For quicker turnaround.",
    "slf-2": "Starlight Fast v2 — Updated fast diffusion model.",
    "slhq-1": "Starlight HQ v1 — Highest quality diffusion restoration. Slower but best results.",
    "slm-1": "Starlight Mini v1 — Lightweight Starlight for shorter clips or quick previews.",
    "slp-2": "Starlight Precise v2 — Precise diffusion with high temporal consistency. Less hallucination.",
    "slp-2.5": "Starlight Precise v2.5 — Updated precise model with improved consistency.",
    # --- Utilities ---
    "stab-1": "Stabilization v1 — Video stabilization. Reduces camera shake and jitter.",
    "remove-1": "Object Removal v1 — AI-based object removal from video.",
    # --- Frame Interpolation ---
    "apo-8": "Apollo v8 — Frame interpolation for slow motion or FPS conversion. Smooth motion synthesis.",
    "apf-2": "Apollo Fast v2 — Faster frame interpolation with good quality.",
    "chf-3": "Chronos Fast v3 — Fast frame interpolation alternative to Apollo.",
    "chr-2": "Chronos v2 — High quality frame interpolation.",
}

def update_model_info():
    sel = itm['ModelCombo'].CurrentText or ""
    code = sel.split()[0] if sel else ""
    info = MODEL_INFO.get(code, "No description available.")
    itm['ModelInfo'].PlainText = info

# Show initial model info
update_model_info()

resolutions = [
    "1080p (1920x1080)",
    "2K (2560x1440)",
    "4K UHD (3840x2160)",
    "4K DCI (4096x2160)",
    "8K (7680x4320)",
    "2x Source",
    "4x Source"
]
for r in resolutions:
    itm['ResCombo'].AddItem(r)

# Populate filter parameter combos
for mode in ["Auto", "Manual", "Relative"]:
    itm['AutoMode'].AddItem(mode)
for c in ["low", "middle", "high"]:
    itm['Creativity'].AddItem(c)
itm['Creativity'].CurrentIndex = 1  # default: middle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def log(msg):
    current = itm['LogText'].PlainText
    itm['LogText'].PlainText = current + msg + "\n"

# Resolution presets: name -> (width, height) or None for scale-based
RES_MAP = {
    "1080p (1920x1080)": (1920, 1080),
    "2K (2560x1440)": (2560, 1440),
    "4K UHD (3840x2160)": (3840, 2160),
    "4K DCI (4096x2160)": (4096, 2160),
    "8K (7680x4320)": (7680, 4320),
    "2x Source": None,
    "4x Source": None,
}

# Models that support creativity parameter
CREATIVE_MODELS = {"slc-1", "hyp-1", "hyp-2", "wonder-1"}

def get_params():
    sel = itm['ModelCombo'].CurrentText or models[0]
    model_code = sel.split()[0]
    res_text = itm['ResCombo'].CurrentText or "4K UHD (3840x2160)"
    try:
        handles = int(itm['Handles'].Text)
    except:
        handles = 0
    api_key = itm['APIKey'].Text
    if api_key and api_key != "YOUR_API_KEY":
        engine.save_api_key(api_key)

    # Build filter params dict
    auto_mode = itm['AutoMode'].CurrentText or "Auto"
    filter_params = {
        "auto_mode": auto_mode,
        "creativity": itm['Creativity'].CurrentText or "middle",
    }

    # Only include slider values if NOT in Auto mode
    if auto_mode != "Auto":
        filter_params["compression"] = itm['Compression'].Value / 100.0
        filter_params["details"] = itm['Details'].Value / 100.0
        filter_params["noise"] = itm['Noise'].Value / 100.0
        filter_params["blur"] = itm['Blur'].Value / 100.0
        filter_params["halo"] = itm['Halo'].Value / 100.0
        filter_params["recoverOriginalDetailValue"] = itm['RecoverDetail'].Value / 100.0
        filter_params["grain"] = itm['Grain'].Value / 1000.0  # 0-100 -> 0-0.1

    return model_code, res_text, handles, api_key, filter_params

def get_output_resolution(res_text, src_w, src_h):
    """Calculate output width and height from the resolution preset."""
    preset = RES_MAP.get(res_text)
    if preset is not None:
        return preset
    # Scale-based
    if "4x" in res_text:
        return (src_w * 4, src_h * 4)
    else:
        return (src_w * 2, src_h * 2)

def process_single_clip(clip_data, model_code, res_text, handles, api_key, filter_params):
    """Process one clip with FFmpeg extraction. Runs SYNCHRONOUSLY."""
    clip_path = clip_data['path']
    clip_fps = clip_data['fps']
    source_start = clip_data['left_offset']
    source_duration = clip_data['duration']
    timeline_start = clip_data['timeline_start']
    track_idx = clip_data['track']

    base_dir = os.path.dirname(clip_path)
    base_name = os.path.splitext(os.path.basename(clip_path))[0]
    src_ext = os.path.splitext(clip_path)[1].lower()
    out_ext = ".mov" if src_ext == ".mov" else ".mp4"
    extracted_path = os.path.join(base_dir, base_name + "_extracted.mp4")
    output_path = os.path.join(base_dir, base_name + "_" + model_code + out_ext)

    # 1. Extract the used portion with FFmpeg
    log("Extracting used portion with FFmpeg...")
    log("  Source start frame: %d, Duration: %d frames, Handles: %d" % (source_start, source_duration, handles))
    engine.extract_clip(clip_path, extracted_path, source_start, source_duration, clip_fps, handles)
    ext_size = os.path.getsize(extracted_path) / 1048576.0
    log("  Extracted: %.1f MB" % ext_size)

    # 2. Probe extracted clip and send to Topaz
    w, h, frames, fps, dur, size = engine.probe_video(extracted_path)
    log("  Extracted clip: %dx%d, %d frames, %.1f sec" % (w, h, frames, dur))

    out_w, out_h = get_output_resolution(res_text, w, h)
    log("Sending to Topaz API (%s, %dx%d -> %dx%d)..." % (model_code, w, h, out_w, out_h))
    log("  Uploading and processing - UI will freeze until complete...")

    req_id = engine.process_topaz_video(extracted_path, output_path, api_key, model_code, out_w=out_w, out_h=out_h, filter_params=filter_params)

    log("Done! Request ID: %s" % req_id)
    log("Output: %s" % output_path)

    # 3. Import to Media Pool
    imported = None
    try:
        imported = media_pool.ImportMedia([output_path])
        log("Imported to Media Pool.")
    except Exception:
        log("Note: Please drag the output file into your Media Pool manually.")

    # 4. Place on track above at same timeline position
    if imported and timeline_start is not None and track_idx is not None:
        try:
            target_track = track_idx + 1
            # Ensure the target track exists
            track_count = timeline.GetTrackCount("video")
            if target_track > track_count:
                timeline.AddTrack("video")
                log("Added new video track %d." % target_track)

            media_pool.AppendToTimeline([{
                "mediaPoolItem": imported[0],
                "startFrame": 0,
                "trackIndex": target_track,
                "recordFrame": timeline_start
            }])
            log("Placed on Video Track %d at frame %d." % (target_track, timeline_start))
        except Exception as e:
            log("Note: Could not auto-place on timeline: %s" % str(e))
            log("  The clip is in your Media Pool - drag it to the timeline manually.")

    # 5. Cleanup extracted temp file
    try:
        if os.path.exists(extracted_path):
            os.remove(extracted_path)
    except Exception:
        pass

    return output_path

# ---------------------------------------------------------------------------
# Button handlers — SYNCHRONOUS (no threads)
# ---------------------------------------------------------------------------
def OnProcessCurrent(ev):
    itm['LogText'].PlainText = ""
    try:
        if not timeline:
            log("Error: No active timeline.")
            return

        current_clip = timeline.GetCurrentVideoItem()
        if not current_clip:
            log("Error: No clip under playhead.")
            return

        mp = current_clip.GetMediaPoolItem()
        if not mp:
            log("Error: Clip has no media file.")
            return

        clip_path = mp.GetClipProperty("File Path")
        if not clip_path:
            log("Error: Could not get file path.")
            return

        model_code, res_text, handles, api_key, filter_params = get_params()

        # Figure out what track this clip is on
        clip_track = 1
        track_count = timeline.GetTrackCount("video")
        for t in range(1, track_count + 1):
            items = timeline.GetItemListInTrack("video", t)
            if items:
                for item in items:
                    if item.GetName() == current_clip.GetName() and item.GetStart() == current_clip.GetStart():
                        clip_track = t
                        break

        clip_data = {
            'name': current_clip.GetName(),
            'path': clip_path,
            'fps': float(mp.GetClipProperty("FPS")),
            'left_offset': current_clip.GetLeftOffset(),
            'duration': current_clip.GetDuration(),
            'timeline_start': current_clip.GetStart(),
            'track': clip_track
        }

        log("Processing: %s" % clip_data['name'])
        log("  Source: %s" % clip_path)
        process_single_clip(clip_data, model_code, res_text, handles, api_key, filter_params)
        log("\n=== COMPLETE ===")

    except Exception as e:
        import traceback
        log("ERROR: " + str(e))
        log(traceback.format_exc())

def OnProcessBatch(ev):
    itm['LogText'].PlainText = ""
    try:
        if not timeline:
            log("Error: No active timeline.")
            return

        try:
            track_idx = int(itm['TrackNum'].Text)
        except:
            log("Error: Track must be a number.")
            return

        clips = timeline.GetItemListInTrack("video", track_idx)
        if not clips:
            log("No clips on track %d." % track_idx)
            return

        model_code, res_text, handles, api_key, filter_params = get_params()

        log("Found %d clips on Track %d." % (len(clips), track_idx))
        log("UI will freeze during processing. This is normal.\n")

        for i, clip in enumerate(clips):
            mp = clip.GetMediaPoolItem()
            if not mp:
                log("Skipping clip %d: no media pool item." % (i+1))
                continue

            clip_path = mp.GetClipProperty("File Path")
            if not clip_path:
                log("Skipping clip %d: no file path." % (i+1))
                continue

            clip_data = {
                'name': clip.GetName(),
                'path': clip_path,
                'fps': float(mp.GetClipProperty("FPS")),
                'left_offset': clip.GetLeftOffset(),
                'duration': clip.GetDuration(),
                'timeline_start': clip.GetStart(),
                'track': track_idx
            }

            log("--- Clip %d/%d: %s ---" % (i+1, len(clips), clip.GetName()))
            try:
                process_single_clip(clip_data, model_code, res_text, handles, api_key, filter_params)
            except Exception as e:
                log("ERROR on clip %d: %s" % (i+1, str(e)))

        log("\n=== BATCH COMPLETE ===")

    except Exception as e:
        import traceback
        log("ERROR: " + str(e))
        log(traceback.format_exc())

def OnClose(ev):
    dispatcher.ExitLoop()

# ---------------------------------------------------------------------------
# Bind & run
# ---------------------------------------------------------------------------
win.On.ProcessBatchBtn.Clicked = OnProcessBatch
win.On.ProcessCurrentBtn.Clicked = OnProcessCurrent
win.On.TopazBatchWin.Close = OnClose

def OnModelChanged(ev):
    update_model_info()
win.On.ModelCombo.CurrentIndexChanged = OnModelChanged

win.Show()
dispatcher.RunLoop()
