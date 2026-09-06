-- Omarchy Voice Assistant Keybindings
-- Add this snippet to your ~/.config/hypr/bindings.lua

-- Push-to-Talk / Tap-to-Talk Voice Command Trigger
o.bind("SUPER + V", "Voice Assistant", { launch = "omarchy-assistant listen" })

-- Alternative: Hold or cancel voice listening
o.bind("SUPER + SHIFT + V", "Stop Voice Listening", { launch = "omarchy-assistant stop-listening" })
