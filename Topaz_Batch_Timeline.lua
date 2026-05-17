local scriptDir = os.getenv("HOME") .. "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
local pythonScript = scriptDir .. "/Topaz_Batch_Timeline.py"

-- Launch the python script directly in the background (osascript is often blocked by macOS privacy settings)
local cmd = '/usr/bin/nohup python3 "' .. pythonScript .. '" > /tmp/topaz_batch.log 2>&1 &'
os.execute(cmd)
