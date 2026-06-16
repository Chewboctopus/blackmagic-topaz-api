"""Topaz API Batch Processor for DaVinci Resolve.

A Fusion script that sends timeline clips to the Topaz Video AI cloud API
for upscaling, enhancement, denoising, frame interpolation, and more.
Run from Workspace > Scripts in DaVinci Resolve.
"""
import sys
import os
import time
import traceback
import datetime as _dt

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
        ui.Label({'Text': 'Safety Padding:', 'Weight': 0.3}),
        ui.CheckBox({'ID': 'SafetyPadCheck', 'Text': 'Add 2 duplicate frames at head/tail (when no handles)', 'Checked': True, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'Text': 'Auto-Trim:', 'Weight': 0.3}),
        ui.CheckBox({'ID': 'AutoTrimCheck', 'Text': 'Auto-trim excess frames on download (diff-matte matching)', 'Checked': True, 'Weight': 0.7})
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

    # --- Frame Interpolation Parameters (Chronos / Apollo) ---
    ui.Label({'ID': 'InterpHeader', 'Text': '── Frame Interpolation ──', 'Weight': 0}),
    ui.HGroup({'Weight': 0, 'ID': 'FPSMultRow'}, [
        ui.Label({'ID': 'FPSMultLabel', 'Text': 'FPS Multiplier:', 'Weight': 0.3}),
        ui.ComboBox({'ID': 'FPSMultCombo', 'Weight': 0.5}),
        ui.CheckBox({'ID': 'LockFPSCheck', 'Text': 'Lock to Slowmo', 'Checked': True, 'Weight': 0.2})
    ]),
    ui.HGroup({'Weight': 0, 'ID': 'SlowmoRow'}, [
        ui.Label({'ID': 'SlowmoLabel', 'Text': 'Slow Motion Factor:', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'SlowmoSpin', 'Value': 1, 'Minimum': 1, 'Maximum': 16, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0, 'ID': 'InterpDupeRow'}, [
        ui.Label({'ID': 'InterpDupeLabel', 'Text': 'Interpolate Dupe Frames:', 'Weight': 0.3}),
        ui.CheckBox({'ID': 'InterpDupeCheck', 'Text': 'Detect and replace duplicate frames', 'Checked': True, 'Weight': 0.7})
    ]),
    ui.HGroup({'Weight': 0, 'ID': 'DupeThreshRow'}, [
        ui.Label({'ID': 'DupeThreshLabel', 'Text': 'Dupe Threshold (0.001-0.1):', 'Weight': 0.3}),
        ui.SpinBox({'ID': 'DupeThreshSpin', 'Value': 3, 'Minimum': 1, 'Maximum': 100, 'Weight': 0.7})
    ]),

    ui.Label({'Text': 'Status:', 'Weight': 0}),
    ui.TextEdit({'ID': 'LogText', 'ReadOnly': True, 'Weight': 1}),
    ui.HGroup({'Weight': 0}, [
        ui.Button({'ID': 'ProcessCurrentBtn', 'Text': 'Process Current Clip', 'Weight': 1}),
        ui.Button({'ID': 'ProcessBatchBtn', 'Text': 'Process Track Batch', 'Weight': 1})
    ]),
    ui.HGroup({'Weight': 0}, [
        ui.Label({'ID': 'LogPathLabel', 'Text': 'Logs: ~/Documents/Topaz_API_Logs/', 'Weight': 0.8}),
        ui.Button({'ID': 'OpenLogsBtn', 'Text': 'Open Logs Folder', 'Weight': 0.2})
    ])
]))

itm = win.GetItems()

# Populate FPS multiplier combo
for mult in ['1x', '2x', '3x', '4x', '8x', '16x']:
    itm['FPSMultCombo'].AddItem(mult)
itm['FPSMultCombo'].CurrentIndex = 0  # default: 1x (locked to slowmo=1)
itm['FPSMultCombo'].Enabled = False  # locked by default

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
    "prob-4": "Proteus v4 -- Versatile all-rounder with full manual controls. Best for low-to-medium quality footage. Supports: compression, details, noise, blur, halo, grain.",
    "pnat-1": "Proteus Natural v1 -- Natural-looking enhancement, less aggressive than standard Proteus. Good for organic footage.",
    # --- Artemis ---
    "ahq-12": "Artemis HQ v12 -- Detail and sharpening for high-quality sources (Blu-ray, ProRes). Preserves existing quality.",
    "alq-13": "Artemis LQ v13 -- Restores low-quality, heavily compressed footage. Good for web video, old DVDs.",
    "alqs-2": "Artemis LQ Dehalo v2 -- Low-quality restoration with halo removal around edges.",
    "amq-13": "Artemis MQ v13 -- Balanced enhancement for medium-quality sources.",
    "amqs-2": "Artemis MQ Dehalo v2 -- Medium-quality with halo reduction.",
    "aaa-9": "Artemis Aliased v9 -- Removes aliasing/jagged edges from low-res footage.",
    "aaa-10": "Artemis Aliased v10 -- Updated anti-aliasing model.",
    "aiob-1": "Artemis IO Balanced v1 -- Balanced input/output enhancement.",
    "aion-1": "Artemis IO Natural v1 -- Natural-looking IO enhancement.",
    # --- Color ---
    "color-1": "Color v1 -- Color correction and enhancement. Improves color accuracy and vibrancy.",
    # --- Dione ---
    "ddv-3": "Dione DV v3 -- Specialized for DV/MiniDV camcorder footage deinterlacing and enhancement.",
    "dtd-4": "Dione TV Detail v4 -- Deinterlace interlaced TV content with detail preservation.",
    "dtds-2": "Dione TV Detail Strong v2 -- Aggressive deinterlacing with strong detail recovery.",
    "dtv-4": "Dione TV v4 -- General TV/broadcast deinterlacing.",
    "dtvs-2": "Dione TV Strong v2 -- Strong deinterlacing for challenging broadcast footage.",
    # --- Gaia ---
    "gcg-5": "Gaia CG v5 -- Optimized for CGI, animation, and anime. Preserves clean lines and flat colors.",
    "ghq-5": "Gaia HQ v5 -- Natural upscaling for high-quality footage to 4K/8K. Preserves organic textures.",
    "ganim-1": "Gaia Anime v1 -- Specialized for anime content. Clean line work, vibrant colors.",
    # --- Hyperion ---
    "hyp-1": "Hyperion v1 -- SDR to HDR conversion. Expands dynamic range and color gamut to HDR10. Supports: creativity.",
    "hyp-2": "Hyperion v2 -- Improved SDR to HDR. Better highlight recovery and shadow detail. Supports: creativity.",
    # --- Iris ---
    "iris-2": "Iris v2 -- Face recovery and fine detail restoration. Great for portrait-heavy footage.",
    "iris-3": "Iris v3 -- Improved face and detail recovery. Best for degraded footage with people.",
    # --- Nyx ---
    "nxf-1": "Nyx Fine v1 -- Fine-grained noise reduction. Preserves subtle details while cleaning noise.",
    "nxl-1": "Nyx Light v1 -- Light denoising for footage with mild noise.",
    "nxhf-1": "Nyx HiFi v1 -- High-fidelity denoising. Maximum detail preservation.",
    "nyx-3": "Nyx v3 -- General denoising for low-light, high-ISO, or grainy footage.",
    # --- Rhea ---
    "rhea-1": "Rhea v1 -- Stabilization and enhancement model.",
    # --- Theia ---
    "thd-3": "Theia Detail v3 -- Maximum detail and sharpness. Best for footage needing extra clarity.",
    "thf-4": "Theia Fidelity v4 -- Faithful enhancement preserving original character. Less aggressive than Detail.",
    "thm-2": "Themis 2 (Motion Deblur) -- Restores clarity to fast-moving footage by reducing motion blur. AI-powered deblur.",
    # --- Wonder ---
    "wonder-1": "Wonder v1 -- Generative enhancement. Creates new detail using AI generation. Supports: creativity.",
    # --- Starlight ---
    "sl-1": "Starlight v1 -- Diffusion-based restoration for severely degraded/archival footage. Rebuilds missing detail.",
    "slc-1": "Astra 1 (slc-1) -- Creative diffusion upscaling for GenAI video. Generates dynamic new texture and detail. Supports: creativity (low/middle/high).",
    "slf-1": "Starlight Fast v1 -- Faster diffusion processing, good quality. For quicker turnaround.",
    "slf-2": "Starlight Fast v2 -- Updated fast diffusion model.",
    "slhq-1": "Starlight HQ v1 -- Highest quality diffusion restoration. Slower but best results.",
    "slm-1": "Starlight Mini v1 -- Lightweight Starlight for shorter clips or quick previews.",
    "slp-2": "Starlight Precise v2 -- Precise diffusion with high temporal consistency. Less hallucination.",
    "slp-2.5": "Starlight Precise v2.5 -- Updated precise model with improved consistency.",
    # --- Utilities ---
    "stab-1": "Stabilization v1 -- Video stabilization. Reduces camera shake and jitter.",
    "remove-1": "Object Removal v1 -- AI-based object removal from video.",
    # --- Frame Interpolation ---
    "apo-8": "Apollo v8 -- Frame interpolation for slow motion or FPS conversion. Smooth motion synthesis.",
    "apf-2": "Apollo Fast v2 -- Faster frame interpolation with good quality.",
    "chf-3": "Chronos Fast v3 -- Fast frame interpolation alternative to Apollo.",
    "chr-2": "Chronos v2 -- High quality frame interpolation.",
}

INTERP_MODELS = {"apo-8", "apf-2", "chf-3", "chr-2"}

# Model capability sets -- defined once, used everywhere
UPSCALE_MODELS = {
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
CREATIVE_MODELS = {"slc-1", "hyp-1", "hyp-2", "wonder-1", "remove-1"}
PROMPT_MODELS = {"remove-1", "wonder-1", "slc-1"}
UTILITY_MODELS = {"stab-1", "remove-1"}

def update_model_info():
    sel = itm['ModelCombo'].CurrentText or ""
    code = sel.split()[0] if sel else ""
    info = MODEL_INFO.get(code, "No description available.")
    itm['ModelInfo'].PlainText = info

    is_interp = code in INTERP_MODELS

    # Determine capabilities for this model
    caps = set()

    if code in UPSCALE_MODELS:
        caps.update(["mode", "compression", "details", "noise", "blur", "halo", "recover", "grain"])
    if code in CREATIVE_MODELS:
        caps.add("creativity")
    if code in PROMPT_MODELS:
        caps.add("prompt")

    # Enable/disable upscale controls (hidden for interp models)
    itm['AutoMode'].Enabled = "mode" in caps and not is_interp
    itm['Creativity'].Enabled = "creativity" in caps and not is_interp
    itm['Prompt'].Enabled = "prompt" in caps and not is_interp
    itm['Compression'].Enabled = "compression" in caps and not is_interp
    itm['Details'].Enabled = "details" in caps and not is_interp
    itm['Noise'].Enabled = "noise" in caps and not is_interp
    itm['Blur'].Enabled = "blur" in caps and not is_interp
    itm['Halo'].Enabled = "halo" in caps and not is_interp
    itm['RecoverDetail'].Enabled = "recover" in caps and not is_interp
    itm['Grain'].Enabled = "grain" in caps and not is_interp
    itm['ResCombo'].Enabled = not is_interp  # Interp keeps source resolution

    # Enable/disable interpolation controls
    # FPS combo: only enabled for interp models AND when not locked
    fps_locked = itm['LockFPSCheck'].Checked
    itm['FPSMultCombo'].Enabled = is_interp and not fps_locked
    itm['LockFPSCheck'].Enabled = is_interp
    itm['SlowmoSpin'].Enabled = is_interp
    itm['InterpDupeCheck'].Enabled = is_interp
    itm['DupeThreshSpin'].Enabled = is_interp

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
itm['ExtractMode'].AddItem("Auto (trim or full source)")
itm['ExtractMode'].AddItem("Full Source Extent (for re-applying speed/reverse)")
itm['ExtractMode'].CurrentIndex = 0  # default: Auto

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Persistent log file -- one per session, kept for debugging / sharing with Topaz dev team
_LOG_DIR = os.path.expanduser("~/Documents/Topaz_API_Logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(
    _LOG_DIR,
    "topaz_batch_%s.log" % _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
)
_log_fh = open(_LOG_FILE, "a", encoding="utf-8")

def log(msg):
    ts = _dt.datetime.now().strftime("%H:%M:%S")
    # Write to UI
    current = itm['LogText'].PlainText
    itm['LogText'].PlainText = current + msg + "\n"
    # Write to persistent log file
    _log_fh.write("[%s] %s\n" % (ts, msg))
    _log_fh.flush()


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
# (model sets defined above as module-level constants)

def get_params():
    sel = itm['ModelCombo'].CurrentText or models[0]
    model_code = sel.split()[0]
    res_text = itm['ResCombo'].CurrentText or "4K UHD (3840x2160)"
    try:
        handles = int(itm['Handles'].Text)
    except ValueError:
        handles = 0
    api_key = itm['APIKey'].Text
    if api_key and api_key != "YOUR_API_KEY":
        engine.save_api_key(api_key)

    is_interp = model_code in INTERP_MODELS

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

    # Interpolation params
    interp_params = {}
    if is_interp:
        fps_mult_text = itm['FPSMultCombo'].CurrentText or "2x"
        interp_params["fps_multiplier"] = int(fps_mult_text.replace("x", ""))
        interp_params["slowmo"] = itm['SlowmoSpin'].Value
        interp_params["interpolate_dupes"] = itm['InterpDupeCheck'].Checked
        interp_params["dupe_threshold"] = itm['DupeThreshSpin'].Value / 1000.0  # 1-100 -> 0.001-0.1

    return model_code, res_text, handles, api_key, filter_params, interp_params, is_interp

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

def find_available_track(timeline, clip_start, clip_end, source_track):
    """Find the lowest video track above source_track with no overlapping clips.

    If all existing tracks are occupied, adds a new video track.
    """
    track_count = timeline.GetTrackCount("video")

    for t in range(source_track + 1, track_count + 1):
        items = timeline.GetItemListInTrack("video", t)
        if not items:
            return t  # empty track -- safe to use
        # Check for overlap with any existing clip
        has_overlap = False
        for item in items:
            item_start = item.GetStart()
            item_end = item.GetEnd()
            if item_start < clip_end and item_end > clip_start:
                has_overlap = True
                break
        if not has_overlap:
            return t  # no overlap on this track

    # All existing tracks occupied -- add a new one
    timeline.AddTrack("video")
    return track_count + 1

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
    # time already imported at module level
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

def process_single_clip(clip_data, model_code, res_text, handles, api_key, filter_params, interp_params=None, is_interp=False):
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

    # Auto-bump handles if extraction will be less than 10 frames (API minimum)
    total_extracted = source_duration + (handles * 2)
    if total_extracted < 10:
        extra_needed = 10 - total_extracted
        handles += (extra_needed + 1) // 2
        log("  *** Auto-increasing handles to %d to meet Topaz 10-frame minimum" % handles)

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
    elif source_start == 0 and handles == 0 and source_duration == clip_data.get('total_source_frames', 0):
        # Full source file -- skip extraction, send directly to Topaz
        # This is common after Render in Place (the clip IS the file)
        log("Using source file directly (no trimming needed).")
        extracted_path = clip_path
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

    # 2a. Save reference frames for auto-trim (before padding)
    head_ref = None
    tail_ref = None
    use_auto_trim = itm['AutoTrimCheck'].Checked
    if use_auto_trim:
        head_ref, tail_ref = engine.extract_reference_frames(extracted_path, base_dir, _log=log)

    # 2b. Safety padding: when no handles are available, add 2 duplicate
    #     frames at head and tail to guard against Topaz dropping frames
    #     at clip boundaries.  The extra frames stay in the output --
    #     trim them in editorial as needed (Topaz frame loss is variable).
    SAFETY_PAD = 2
    padded_path = None
    topaz_input_path = extracted_path

    use_safety_pad = itm['SafetyPadCheck'].Checked
    if use_safety_pad and handles == 0:
        padded_path = os.path.join(base_dir, base_name + "_padded.mp4")
        log("  No handles -- adding %d safety frames to head and tail..." % SAFETY_PAD)
        engine.pad_clip_with_safety_frames(extracted_path, padded_path, fps, pad_frames=SAFETY_PAD)
        pad_w, pad_h, pad_frames_total, pad_fps, pad_dur, pad_size = engine.probe_video(padded_path)
        log("  Padded clip: %d frames (was %d), %.1f sec" % (pad_frames_total, frames, pad_dur))
        topaz_input_path = padded_path

    if is_interp and interp_params:
        # --- Frame Interpolation path (Chronos / Apollo) ---
        fps_mult = interp_params.get("fps_multiplier", 2)
        slowmo = interp_params.get("slowmo", 1)
        interp_dupes = interp_params.get("interpolate_dupes", True)
        dupe_thresh = interp_params.get("dupe_threshold", 0.01)
        log("Sending to Topaz API -- Interpolation (%s, %dx FPS, slowmo=%d, dupes=%s)..." % (
            model_code, fps_mult, slowmo, interp_dupes))
        req_id = engine.process_topaz_interpolation(
            topaz_input_path, output_path, api_key, model_code,
            fps_multiplier=fps_mult, slowmo=slowmo,
            interpolate_dupes=interp_dupes, dupe_threshold=dupe_thresh,
            progress_callback=log
        )
    else:
        # --- Upscale / Enhancement path ---
        out_w, out_h = get_output_resolution(res_text, w, h)
        log("Sending to Topaz API (%s, %dx%d -> %dx%d)..." % (model_code, w, h, out_w, out_h))
        req_id = engine.process_topaz_video(topaz_input_path, output_path, api_key, model_code, out_w=out_w, out_h=out_h, filter_params=filter_params, progress_callback=log)

    log("Done! Request ID: %s" % req_id)

    # 2c. Frame count comparison: uploaded vs downloaded
    uploaded_frames = frames  # from the pre-upload probe
    if padded_path:
        uploaded_frames = pad_frames_total  # if padded, we sent the padded count
    out_w2, out_h2, downloaded_frames, out_fps, out_dur, out_size = engine.probe_video(output_path)
    log("")
    log("  === FRAME COUNT REPORT ===")
    log("  Uploaded to Topaz:   %d frames (%dx%d, %.2f fps)" % (uploaded_frames, w, h, fps))
    log("  Downloaded from Topaz: %d frames (%dx%d, %.2f fps)" % (downloaded_frames, out_w2, out_h2, out_fps))
    frame_diff = downloaded_frames - uploaded_frames
    if frame_diff == 0:
        log("  Discrepancy: NONE (frame counts match)")
    elif frame_diff < 0:
        log("  Discrepancy: %d frames LOST by Topaz" % abs(frame_diff))
    else:
        log("  Discrepancy: %d frames ADDED by Topaz" % frame_diff)
    if padded_path:
        log("  (Safety padding was ON: %d frames added at head + %d at tail before upload)" % (SAFETY_PAD, SAFETY_PAD))
        original_expected = frames
        effective_output = downloaded_frames
        log("  Original source frames: %d | Topaz output frames: %d" % (original_expected, effective_output))
    log("  ===========================")
    log("")

    # 2d. Auto-trim excess frames
    if use_auto_trim and head_ref and tail_ref:
        fps_mult = 1
        if is_interp and interp_params:
            fps_mult = interp_params.get("fps_multiplier", 1)
        output_path, final_frame_count = engine.auto_trim_output(
            output_path, frames, head_ref, tail_ref,
            fps, safety_pad=SAFETY_PAD if padded_path else 0,
            fps_multiplier=fps_mult, _log=log
        )

    # Cleanup temp files
    if padded_path:
        try:
            if os.path.exists(padded_path):
                os.remove(padded_path)
        except Exception:
            pass
    # Cleanup reference frame PNGs
    for ref_file in [head_ref, tail_ref]:
        if ref_file:
            try:
                if os.path.exists(ref_file):
                    os.remove(ref_file)
            except Exception:
                pass

    log("Output: %s" % output_path)

    # 3. Import to Media Pool
    imported = None
    try:
        imported = media_pool.ImportMedia([output_path])
        log("Imported to Media Pool.")
    except Exception:
        log("Note: Please drag the output file into your Media Pool manually.")

    # 4. Place on the lowest available track without overwriting
    if imported and timeline_start is not None and track_idx is not None:
        try:
            timeline_end = clip_data['timeline_end']
            target_track = find_available_track(timeline, timeline_start, timeline_end, track_idx)

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

    # 5. Cleanup extracted temp file (but NOT the source file)
    try:
        if extracted_path != clip_path and os.path.exists(extracted_path):
            os.remove(extracted_path)
    except Exception:
        pass

    return output_path

# ---------------------------------------------------------------------------
# Button handlers -- SYNCHRONOUS (no threads)
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

        model_code, res_text, handles, api_key, filter_params, interp_params, is_interp = get_params()

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
        has_speed_effect = (source_duration != timeline_duration)
        if has_speed_effect:
            clip_speed = (source_duration / float(timeline_duration)) * 100.0
        else:
            clip_speed = 100.0

        # Determine extraction mode
        extract_text = itm['ExtractMode'].CurrentText or ""
        force_full_extent = "Full Source" in extract_text

        log("  Source: left=%d, right=%d, total=%d -> source_duration=%d (timeline=%d)" % (
            left_offset, right_offset, total_source_frames, source_duration, timeline_duration))

        if has_speed_effect:
            log("  Speed/reverse effect detected: %.0f%%" % clip_speed)

            if force_full_extent:
                # User chose to extract all source frames -- they'll re-apply speed/reverse
                log("  Mode: Full Source Extent -- extracting all %d source frames" % source_duration)
                log("  (Re-apply speed/reverse to enhanced clip after Topaz processing)")
            else:
                # Auto mode: abort with instructions
                log("")
                log("  *** Speed/reverse detected -- cannot extract with correct timing.")
                log("  *** Choose one:")
                log("  ***   1. Right-click clip > 'Render in Place' first, then re-run")
                log("  ***   2. Switch Extraction to 'Full Source Extent' to get all")
                log("  ***      source frames, then re-apply speed/reverse to the result")
                log("")
                log("  Aborted.")
                return
        else:
            log("  Straight cut -- extracting with FFmpeg")

        clip_data = {
            'name': current_clip.GetName(),
            'path': clip_path,
            'fps': float(mp.GetClipProperty("FPS")),
            'left_offset': left_offset,
            'duration': source_duration,
            'total_source_frames': total_source_frames,
            'timeline_start': timeline_start_frame,
            'timeline_end': timeline_end_frame,
            'track': clip_track,
            'speed': clip_speed,
            'use_resolve_render': False
        }

        log("Processing: %s" % clip_data['name'])
        log("  Source: %s" % clip_path)
        process_single_clip(clip_data, model_code, res_text, handles, api_key, filter_params, interp_params, is_interp)
        log("\n=== COMPLETE ===")

    except Exception as e:
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
        except ValueError:
            log("Error: Track must be a number.")
            return

        clips = timeline.GetItemListInTrack("video", track_idx)
        if not clips:
            log("No clips on track %d." % track_idx)
            return

        model_code, res_text, handles, api_key, filter_params, interp_params, is_interp = get_params()

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
            force_full_extent = "Full Source" in extract_text

            # Skip speed/reverse clips in Auto mode
            if source_duration != timeline_duration and not force_full_extent:
                log("  *** Skipping: speed/reverse detected. Use 'Full Source Extent' or Render in Place.")
                continue

            clip_data = {
                'name': clip.GetName(),
                'path': clip_path,
                'fps': float(mp.GetClipProperty("FPS")),
                'left_offset': left_offset,
                'duration': source_duration,
                'total_source_frames': total_source_frames,
                'timeline_start': clip.GetStart(),
                'timeline_end': clip.GetEnd(),
                'track': track_idx,
                'speed': clip_speed,
                'use_resolve_render': False
            }

            log("--- Clip %d/%d: %s ---" % (i+1, len(clips), clip.GetName()))
            try:
                process_single_clip(clip_data, model_code, res_text, handles, api_key, filter_params, interp_params, is_interp)
            except Exception as e:
                log("ERROR on clip %d: %s" % (i+1, str(e)))

        log("\n=== BATCH COMPLETE ===")

    except Exception as e:
        log("ERROR: " + str(e))
        log(traceback.format_exc())

def OnClose(ev):
    _log_fh.flush()
    _log_fh.close()
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

def OnOpenLogs(ev):
    import subprocess
    subprocess.Popen(["open", _LOG_DIR])
win.On.OpenLogsBtn.Clicked = OnOpenLogs

def _sync_fps_to_slowmo():
    """When locked, set FPS multiplier combo to match slowmo value."""
    slowmo = itm['SlowmoSpin'].Value
    # Map slowmo value to combo index: 1x=0, 2x=1, 3x=2, 4x=3, 8x=4, 16x=5
    fps_map = {1: 0, 2: 1, 3: 2, 4: 3, 8: 4, 16: 5}
    idx = fps_map.get(slowmo, 1)  # default to 2x if not exact match
    itm['FPSMultCombo'].CurrentIndex = idx

def OnSlowmoChanged(ev):
    if itm['LockFPSCheck'].Checked:
        _sync_fps_to_slowmo()
win.On.SlowmoSpin.ValueChanged = OnSlowmoChanged

def OnLockFPSChanged(ev):
    is_interp = itm['ModelCombo'].CurrentText.split()[0] in INTERP_MODELS if itm['ModelCombo'].CurrentText else False
    if itm['LockFPSCheck'].Checked:
        itm['FPSMultCombo'].Enabled = False
        _sync_fps_to_slowmo()
    else:
        itm['FPSMultCombo'].Enabled = is_interp
win.On.LockFPSCheck.Clicked = OnLockFPSChanged

win.Show()
if _new_model_notice:
    itm['LogText'].PlainText = _new_model_notice + "\n"
dispatcher.RunLoop()
