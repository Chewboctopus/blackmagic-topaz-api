# DaVinci Resolve — Topaz Video AI Batch Processor

A native Python script for DaVinci Resolve Studio that sends timeline clips to the [Topaz Video AI API](https://www.topazlabs.com/topaz-video-ai) for upscaling, enhancement, and frame interpolation — then automatically imports and places the results back on your timeline.

## Features

- **40+ Topaz Models** — Full support for Proteus, Artemis, Gaia, Iris, Nyx, Theia, Starlight/Astra, Dione, Hyperion, Wonder, and more. The script also polls the live API on startup to detect any new models not yet in its hardcoded list.
- **Frame Interpolation** — Chronos and Apollo models for FPS multiplication (2x–16x), slow motion, and duplicate frame replacement.
- **Single Clip or Batch** — Process the clip under the playhead, or batch-process every clip on a selected video track.
- **Smart Extraction** — FFmpeg source-copy extraction with configurable frame handles. Automatically detects speed/reverse effects and offers safe workarounds.
- **Auto Timeline Placement** — Imports the enhanced clip into your Media Pool and places it on the track above at the correct timeline position.
- **Filter Controls** — Full manual tuning for supported models: compression, details, noise, blur/sharpen, halo, recover original detail, grain amount, creativity, and text prompts.
- **Format Matching** — Automatically matches output container and codec to your source (ProRes for .mov, H.265 for .mp4).
- **Progress Tracking** — Live processing percentage, time estimates, and stall detection during Topaz API jobs.
- **API Key Persistence** — Saves your Topaz API key locally so you only enter it once.

## Files

| File | Purpose |
|------|---------|
| `Topaz_Batch_Timeline.py` | Main script — UI, clip analysis, timeline logic, button handlers |
| `_topaz_resolve_engine.py` | Engine library — FFmpeg extraction, ffprobe, Topaz API communication (upload, poll, download), API key storage |
| `Topaz_Batch_Timeline.lua` | Lua launcher stub (calls the Python script from Resolve's Script menu) |
| `TopazEnhance.setting` | Fusion macro preset for Topaz enhancement |

## Installation

1. Copy `Topaz_Batch_Timeline.py` into your DaVinci Resolve Scripts folder:
   - **Mac:** `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/`
   - **Windows:** `%appdata%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\`

2. Create a `topaz_lib` subfolder inside the Utility folder and place `_topaz_resolve_engine.py` inside it:
   ```
   Scripts/Utility/
   ├── Topaz_Batch_Timeline.py
   └── topaz_lib/
       └── _topaz_resolve_engine.py
   ```

3. Ensure [FFmpeg](https://ffmpeg.org/) is installed and accessible (the script checks `/opt/homebrew/bin/` and `/usr/local/bin/` on macOS).

4. Restart DaVinci Resolve.

## Usage

1. Open DaVinci Resolve Studio and load a project with a timeline.
2. Go to **Workspace → Scripts → Topaz_Batch_Timeline**.
3. Enter your [Topaz API key](https://www.topazlabs.com/developers) (saved automatically for future sessions).
4. Select a **model** — the info box will show a description and supported parameters.
5. Configure output resolution and filter parameters as needed.
6. Click **Process Current Clip** (clip under playhead) or **Process Track Batch** (all clips on the selected track).
7. The script will extract, upload to Topaz, poll for completion, download the result, import it, and place it on the track above.

### Frame Interpolation (Chronos / Apollo)

When you select an interpolation model (`apo-8`, `apf-2`, `chf-3`, `chr-2`), the UI switches to interpolation controls:

- **FPS Multiplier** — 1x through 16x output frame rate
- **Slow Motion Factor** — 1 = normal speed, 2 = half speed, etc.
- **Interpolate Duplicate Frames** — AI-detects and replaces duplicate/repeated frames
- **Duplicate Threshold** — Sensitivity for duplicate detection (lower = more aggressive)

### Speed / Reverse Effects

If a clip has a speed change or reverse applied, the script detects it and offers two options:

1. **Render in Place** first (right-click clip → Render in Place), then re-run the script on the flattened clip.
2. Switch **Extraction** to **Full Source Extent** to extract all source frames, then re-apply speed/reverse to the enhanced result manually.

## Supported Models

<details>
<summary>Click to expand full model list</summary>

### Upscale / Enhancement
| Code | Name | Notes |
|------|------|-------|
| `prob-4` | Proteus v4 | All-rounder with full manual controls |
| `pnat-1` | Proteus Natural v1 | Natural-looking enhancement |
| `ahq-12` | Artemis HQ v12 | High-quality sources (Blu-ray, ProRes) |
| `alq-13` | Artemis LQ v13 | Low-quality / heavily compressed footage |
| `amq-13` | Artemis MQ v13 | Medium-quality sources |
| `gcg-5` | Gaia CG v5 | CGI, animation, anime |
| `ghq-5` | Gaia HQ v5 | Natural upscaling to 4K/8K |
| `ganim-1` | Gaia Anime v1 | Anime-specialized |
| `iris-3` | Iris v3 | Face recovery and detail restoration |
| `nyx-3` | Nyx v3 | General denoising (low-light, high-ISO) |
| `thd-3` | Theia Detail v3 | Maximum detail and sharpness |
| `thf-4` | Theia Fidelity v4 | Faithful enhancement |
| `thm-2` | Themis v2 | Motion deblur |
| `wonder-1` | Wonder v1 | Generative AI enhancement |

### Starlight / Astra (Diffusion)
| Code | Name | Notes |
|------|------|-------|
| `sl-1` | Starlight v1 | Diffusion restoration for archival footage |
| `slc-1` | Astra 1 | Creative diffusion for GenAI video |
| `slhq-1` | Starlight HQ v1 | Highest quality diffusion |
| `slp-2.5` | Starlight Precise v2.5 | High temporal consistency |

### Deinterlacing (Dione)
| Code | Name | Notes |
|------|------|-------|
| `ddv-3` | Dione DV v3 | DV/MiniDV camcorder footage |
| `dtd-4` | Dione TV Detail v4 | TV content with detail preservation |
| `dtv-4` | Dione TV v4 | General broadcast deinterlacing |

### Frame Interpolation
| Code | Name | Notes |
|------|------|-------|
| `apo-8` | Apollo v8 | Smooth motion synthesis |
| `apf-2` | Apollo Fast v2 | Faster interpolation |
| `chf-3` | Chronos Fast v3 | Fast alternative to Apollo |
| `chr-2` | Chronos v2 | High quality interpolation |

### Utilities
| Code | Name | Notes |
|------|------|-------|
| `hyp-2` | Hyperion v2 | SDR → HDR conversion |
| `stab-1` | Stabilization v1 | Camera shake reduction |
| `remove-1` | Object Removal v1 | AI object removal |
| `color-1` | Color v1 | Color correction |

</details>

## Requirements

- **DaVinci Resolve Studio** (Python scripting requires Studio)
- **Python 3.6+** linked to DaVinci Resolve (Preferences → System → General)
- **FFmpeg / ffprobe** installed
- **Topaz Video AI API key** — [Get one here](https://www.topazlabs.com/developers)
- Python `requests` module (`pip install requests`)

## License

MIT
