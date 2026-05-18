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
    'Geometry': [100, 50, 700, 850],
}, ui.VGroup([
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Select Video Track:', 'Weight': 0.3}),
        ui.LineEdit({'ID': 'TrackNum', 'Text': '1', 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Topaz Model:', 'Weight': 0.3}),
        ui.ComboBox({'ID': 'ModelCombo', 'Weight': 0.7})
    ]),
    ui.TextEdit({'ID': 'ModelInfo', 'ReadOnly': True, 'Weight': 0.15}),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Output Resolution:', 'Weight': 0.3}),
        ui.ComboBox({'ID': 'ResCombo', 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Handles (Frames):', 'Weight': 0.3}),
        ui.LineEdit({'ID': 'Handles', 'Text': '0', 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Extraction:', 'Weight': 0.3}),
        ui.ComboBox({'ID': 'ExtractMode', 'Weight': 0.7})
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
        ui.Label({'Text': 'Prompt:', 'Weight': 0.3}),
        ui.LineEdit({'ID': 'Prompt', 'PlaceholderText': '(for generative/removal models)', 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0, 'ID': 'CompressionRow'}, [
        ui.Label({'ID': 'CompressionLabel', 'Text': 'Compression (-1 to 1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'Compression', 'Value': 0, 'Minimum': -100, 'Maximum': 100, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0, 'ID': 'DetailsRow'}, [
        ui.Label({'ID': 'DetailsLabel', 'Text': 'Details (-1 to 1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'Details', 'Value': 0, 'Minimum': -100, 'Maximum': 100, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0, 'ID': 'NoiseRow'}, [
        ui.Label({'ID': 'NoiseLabel', 'Text': 'Noise (-1 to 1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'Noise', 'Value': 0, 'Minimum': -100, 'Maximum': 100, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0, 'ID': 'BlurRow'}, [
        ui.Label({'ID': 'BlurLabel', 'Text': 'Blur/Sharpen (-1 to 1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'Blur', 'Value': 0, 'Minimum': -100, 'Maximum': 100, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0, 'ID': 'HaloRow'}, [
        ui.Label({'ID': 'HaloLabel', 'Text': 'Halo (-1 to 1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'Halo', 'Value': 0, 'Minimum': -100, 'Maximum': 100, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0, 'ID': 'RecoverRow'}, [
        ui.Label({'ID': 'RecoverLabel', 'Text': 'Recover Original (0-1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'RecoverDetail', 'Value': 0, 'Minimum': 0, 'Maximum': 100, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0, 'ID': 'GrainRow'}, [
        ui.Label({'ID': 'GrainLabel', 'Text': 'Grain Amount (0-0.1):', 'Weight': 0.3}),
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
    "thm-2 (Themis Motion Deblur v2)",
    "wonder-1 (Wonder v1)",
    # --- Starlight / Astra ---
    "sl-1 (Starlight v1)",
    "slc-1 (Astra 1 / Starlight Creative v1)",
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

# Poll the live API for new models not in our hardcoded list
_new_model_notice = ""
try:
    import requests as _req
    _api_key = engine.get_api_key()
    if _api_key:
        _resp = _req.get("https://api.topazlabs.com/video/status",
                         headers={"X-API-Key": _api_key}, timeout=5)
        if _resp.status_code == 200:
            _live_models = set(_resp.json().get("supportedModels", []))
            _known_codes = set(m.split()[0] for m in models)
            _new_codes = _live_models - _known_codes
            if _new_codes:
                for nc in sorted(_new_codes):
                    itm['ModelCombo'].AddItem(nc + " (New!)")
                _new_model_notice = (
                    "New model(s) detected: %s\n"
                    "Check https://developer.topazlabs.com/ for details."
                ) % ", ".join(sorted(_new_codes))
except Exception:
    pass  # Don't block startup if API is unreachable

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
    "thm-2": "Themis 2 (Motion Deblur) — Restores clarity to fast-moving footage by reducing motion blur. AI-powered deblur.",
    # --- Wonder ---
    "wonder-1": "Wonder v1 — Generative enhancement. Creates new detail using AI generation. Supports: creativity.",
    # --- Starlight ---
    "sl-1": "Starlight v1 — Diffusion-based restoration for severely degraded/archival footage. Rebuilds missing detail.",
    "slc-1": "Astra 1 (slc-1) — Creative diffusion upscaling for GenAI video. Generates dynamic new texture and detail. Supports: creativity (low/middle/high).",
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

    # Determine capabilities for this model
    caps = set()
    # Upscale/enhancement models support manual tuning
    upscale_models = {
        "prob-4", "pnat-1",
        "ahq-12", "alq-13", "alqs-2", "amq-13", "amqs-2",
        "aaa-9", "aaa-10", "aiob-1", "aion-1",
        "gcg-5", "ghq-5", "ganim-1",
        "iris-2", "iris-3",
        "nxf-1", "nxl-1", "nxhf-1", "nyx-3",
        "rhea-1",
        "thd-3", "thf-4", "thm-2",
        "color-1",
        "ddv-3", "dtd-4", "dtds-2", "dtv-4", "dtvs-2",
        "sl-1", "slc-1", "slf-1", "slf-2", "slhq-1", "slm-1", "slp-2", "slp-2.5",
        "hyp-1", "hyp-2", "wonder-1",
    }
    creative_models = {"slc-1", "hyp-1", "hyp-2", "wonder-1", "remove-1"}
    prompt_models = {"remove-1", "wonder-1"}
    interp_models = {"apo-8", "apf-2", "chf-3", "chr-2"}
    utility_models = {"stab-1", "remove-1"}

    if code in upscale_models:
        caps.update(["mode", "compression", "details", "noise", "blur", "halo", "recover", "grain"])
    if code in creative_models:
        caps.add("creativity")
    if code in prompt_models:
        caps.add("prompt")

    # Enable/disable controls based on capabilities
    itm['AutoMode'].Enabled = "mode" in caps
    itm['Creativity'].Enabled = "creativity" in caps
    itm['Prompt'].Enabled = "prompt" in caps
    itm['Compression'].Enabled = "compression" in caps
    itm['Details'].Enabled = "details" in caps
    itm['Noise'].Enabled = "noise" in caps
    itm['Blur'].Enabled = "blur" in caps
    itm['Halo'].Enabled = "halo" in caps
    itm['RecoverDetail'].Enabled = "recover" in caps
    itm['Grain'].Enabled = "grain" in caps

# Show initial model info and set control states
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

# Populate extraction mode combo
itm['ExtractMode'].AddItem("Source Copy (FFmpeg) — fast, no effects")
itm['ExtractMode'].AddItem("Timeline Render (Resolve) — bakes speed/reverse/grades")
itm['ExtractMode'].CurrentIndex = 0  # default: FFmpeg

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

    # Include prompt if provided
    prompt_text = itm['Prompt'].Text
    if prompt_text and prompt_text.strip():
        filter_params["prompt"] = prompt_text.strip()

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

def render_clip_via_resolve(clip_data, output_path):
    """Render a clip range via Resolve's Deliver page. Bakes ALL timeline effects."""
    timeline_start = clip_data['timeline_start']
    timeline_end = clip_data['timeline_end']
    clip_fps = clip_data['fps']

    project = resolve.GetProjectManager().GetCurrentProject()

    # Save current page
    prev_page = resolve.GetCurrentPage()

    # Set render settings: DNxHR HQ in MXF for quality, or QuickTime ProRes
    render_settings = {
        "SelectAllFrames": False,
        "MarkIn": timeline_start,
        "MarkOut": timeline_end - 1,  # Resolve uses inclusive end
        "TargetDir": os.path.dirname(output_path),
        "CustomName": os.path.splitext(os.path.basename(output_path))[0],
        "FormatWidth": 0,   # 0 = same as timeline
        "FormatHeight": 0,
        "ExportVideo": True,
        "ExportAudio": False,
    }

    # Try QuickTime/ProRes first, fall back to mp4
    src_ext = os.path.splitext(clip_data['path'])[1].lower()
    if src_ext == ".mov":
        render_settings["VideoFormat"] = "QuickTime"
        render_settings["VideoCodec"] = "Apple ProRes 422 HQ"
    else:
        render_settings["VideoFormat"] = "mp4"
        render_settings["VideoCodec"] = "H.265"

    project.SetRenderSettings(render_settings)
    job_id = project.AddRenderJob()
    if not job_id:
        raise Exception("Failed to add render job. Check Deliver page settings.")

    project.StartRendering(job_id)

    # Poll for completion
    import time
    while project.IsRenderingInProgress():
        time.sleep(1)

    # Check result
    job_info = project.GetRenderJobStatus(job_id)
    status = job_info.get("JobStatus", "Unknown") if job_info else "Unknown"
    if status != "Complete":
        raise Exception("Render failed with status: %s" % status)

    # Find the rendered file
    rendered_file = job_info.get("OutputFilename", "")
    if not rendered_file or not os.path.exists(rendered_file):
        # Try to find it by the custom name
        target_dir = os.path.dirname(output_path)
        custom_name = os.path.splitext(os.path.basename(output_path))[0]
        for f in os.listdir(target_dir):
            if f.startswith(custom_name) and not f.endswith("_extracted.mp4"):
                rendered_file = os.path.join(target_dir, f)
                break

    # Restore previous page
    try:
        resolve.OpenPage(prev_page)
    except Exception:
        pass

    # Delete the render job to clean up
    try:
        project.DeleteRenderJob(job_id)
    except Exception:
        pass

    return rendered_file

def process_single_clip(clip_data, model_code, res_text, handles, api_key, filter_params):
    """Process one clip. Runs SYNCHRONOUSLY."""
    clip_path = clip_data['path']
    clip_fps = clip_data['fps']
    source_start = clip_data['left_offset']
    source_duration = clip_data['duration']
    timeline_start = clip_data['timeline_start']
    track_idx = clip_data['track']
    use_resolve_render = clip_data.get('use_resolve_render', False)

    base_dir = os.path.dirname(clip_path)
    base_name = os.path.splitext(os.path.basename(clip_path))[0]
    src_ext = os.path.splitext(clip_path)[1].lower()
    out_ext = ".mov" if src_ext == ".mov" else ".mp4"
    extracted_path = os.path.join(base_dir, base_name + "_extracted.mp4")
    output_path = os.path.join(base_dir, base_name + "_" + model_code + out_ext)

    if use_resolve_render:
        # --- Timeline Render mode: bakes all effects ---
        log("Rendering via Resolve Deliver page...")
        log("  Timeline range: %d - %d (%d frames)" % (
            timeline_start, clip_data['timeline_end'], clip_data['timeline_end'] - timeline_start))
        rendered_path = render_clip_via_resolve(clip_data, extracted_path)
        if not rendered_path or not os.path.exists(rendered_path):
            raise Exception("Resolve render produced no output file")
        extracted_path = rendered_path
        ext_size = os.path.getsize(extracted_path) / 1048576.0
        log("  Rendered: %.1f MB" % ext_size)
    else:
        # --- FFmpeg source copy mode: fast, no effects ---
        log("Extracting source frames with FFmpeg...")
        log("  Source start frame: %d, Duration: %d frames, Handles: %d" % (
            source_start, source_duration, handles))
        engine.extract_clip(clip_path, extracted_path, source_start, source_duration, clip_fps, handles)
        ext_size = os.path.getsize(extracted_path) / 1048576.0
        log("  Extracted: %.1f MB" % ext_size)

    # 2. Probe extracted clip and send to Topaz
    w, h, frames, fps, dur, size = engine.probe_video(extracted_path)
    log("  Clip to process: %dx%d, %d frames, %.1f sec" % (w, h, frames, dur))

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

        # ---- Determine source frames to extract ----
        left_offset = current_clip.GetLeftOffset()
        right_offset = current_clip.GetRightOffset()
        timeline_duration = current_clip.GetDuration()
        timeline_start_frame = current_clip.GetStart()
        timeline_end_frame = current_clip.GetEnd()

        # Get total source frame count
        total_source_frames = 0
        try:
            fc = mp.GetClipProperty("Frames")
            if fc:
                total_source_frames = int(fc)
        except Exception:
            pass

        # EDL-style source math:
        # source_duration = total_source_frames - left_offset - right_offset
        # This gives us ALL source frames between IN and OUT, regardless of speed
        if total_source_frames > 0:
            source_duration = total_source_frames - left_offset - right_offset
        else:
            source_duration = timeline_duration

        # Detect speed from source vs timeline duration
        if timeline_duration > 0 and source_duration != timeline_duration:
            clip_speed = (source_duration / float(timeline_duration)) * 100.0
        else:
            clip_speed = 100.0

        # Determine extraction mode
        extract_text = itm['ExtractMode'].CurrentText or ""
        use_resolve_render = "Timeline Render" in extract_text

        # Auto-detect speed/reverse: if source_duration != timeline_duration,
        # FFmpeg cannot handle this correctly
        has_speed_effect = (source_duration != timeline_duration)
        if has_speed_effect and not use_resolve_render:
            log("  *** Speed/reverse effect detected! (source=%d vs timeline=%d)" % (
                source_duration, timeline_duration))
            log("  *** FFmpeg cannot extract speed/reverse effects correctly.")
            log("  ***")
            log("  *** Options:")
            log("  ***   1. Switch Extraction to 'Timeline Render' and re-run")
            log("  ***   2. Right-click the clip > 'Render in Place' first,")
            log("  ***      then run Topaz on the rendered flat clip")
            log("  ***")
            log("  *** Aborting to prevent incorrect extraction.")
            return

        log("  Source: left=%d, right=%d, total=%d -> source_duration=%d (timeline=%d)" % (
            left_offset, right_offset, total_source_frames, source_duration, timeline_duration))
        if clip_speed != 100.0:
            log("  Speed effect: %.0f%%" % clip_speed)
        log("  Extraction: %s" % ("Resolve Render" if use_resolve_render else "FFmpeg"))

        clip_data = {
            'name': current_clip.GetName(),
            'path': clip_path,
            'fps': float(mp.GetClipProperty("FPS")),
            'left_offset': left_offset,
            'duration': source_duration,
            'timeline_start': timeline_start_frame,
            'timeline_end': timeline_end_frame,
            'track': clip_track,
            'speed': clip_speed,
            'use_resolve_render': use_resolve_render
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

            # Calculate source IN/OUT like an EDL
            left_offset = clip.GetLeftOffset()
            right_offset = clip.GetRightOffset()
            timeline_duration = clip.GetDuration()

            total_source_frames = 0
            try:
                fc = mp.GetClipProperty("Frames")
                if fc:
                    total_source_frames = int(fc)
            except Exception:
                pass

            if total_source_frames > 0:
                source_duration = total_source_frames - left_offset - right_offset
            else:
                source_duration = timeline_duration

            if timeline_duration > 0 and source_duration != timeline_duration:
                clip_speed = (source_duration / float(timeline_duration)) * 100.0
            else:
                clip_speed = 100.0

            # Determine extraction mode
            extract_text = itm['ExtractMode'].CurrentText or ""
            use_resolve_render = "Timeline Render" in extract_text

            # Auto-detect speed/reverse — skip in FFmpeg mode
            if source_duration != timeline_duration and not use_resolve_render:
                log("  *** Skipping: speed/reverse effect detected. Use Timeline Render mode.")
                continue

            clip_data = {
                'name': clip.GetName(),
                'path': clip_path,
                'fps': float(mp.GetClipProperty("FPS")),
                'left_offset': left_offset,
                'duration': source_duration,
                'timeline_start': clip.GetStart(),
                'timeline_end': clip.GetEnd(),
                'track': track_idx,
                'speed': clip_speed,
                'use_resolve_render': use_resolve_render
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
if _new_model_notice:
    itm['LogText'].PlainText = _new_model_notice + "\n"
dispatcher.RunLoop()
