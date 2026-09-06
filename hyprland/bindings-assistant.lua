-- Omarchy Voice Assistant Keybindings
-- Add this snippet to your ~/.config/hypr/bindings.lua

-- Push-to-Talk / Tap-to-Talk Voice Command Trigger
o.bind("SUPER + A", "Voice Assistant", { launch = "omarchy-assistant listen" })

-- Alternative: Cancel voice listening
o.bind("SUPER + SHIFT + A", "Stop Voice Listening", { launch = "omarchy-assistant stop-listening" })
