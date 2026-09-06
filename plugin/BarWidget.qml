import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "harshjsh01.assistant"

  property string currentState: "idle"

  // Poll state or react to assistant trigger
  Timer {
    interval: 2000
    running: true
    repeat: true
    onTriggered: {
      var proc = Quickshell.exec(["omarchy-shell", "-q", "assistant", "state"])
      proc.finished.connect(function() {
        var s = (proc.stdout || "").trim()
        if (s !== "") root.currentState = s
      })
    }
  }

  readonly property bool isListening: currentState === "listening"
  readonly property bool isProcessing: currentState === "processing" || currentState === "executing"

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.isListening ? "󰍬" : (root.isProcessing ? "󰚩" : "󰍬")
    active: root.isListening || root.isProcessing
    tooltipText: {
      if (root.isListening) return "Voice Assistant: Listening..."
      if (root.isProcessing) return "Voice Assistant: Thinking & Executing..."
      return "Voice Assistant (Click to speak / Super+A)"
    }

    onPressed: function(mouseButton) {
      if (mouseButton === Qt.RightButton) {
        Quickshell.execDetached(["omarchy-assistant", "status"])
      } else {
        Quickshell.execDetached(["omarchy-assistant", "listen"])
      }
    }
  }
}
