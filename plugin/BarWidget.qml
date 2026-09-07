import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "harshjsh01.assistant"

  property string currentState: "idle"

  Process {
    id: statusProc
    command: ["omarchy-shell", "-q", "assistant", "state"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: function() {
        var s = (text || "").trim()
        if (s !== "") root.currentState = s
      }
    }
  }

  Timer {
    interval: 500
    running: true
    repeat: true
    onTriggered: {
      if (!statusProc.running) statusProc.running = true
    }
  }

  readonly property bool isListening: currentState === "listening"
  readonly property bool isProcessing: currentState === "processing" || currentState === "executing" || currentState === "speaking"

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Component {
    id: threeDotsComponent
    Row {
      spacing: 2.5
      anchors.centerIn: parent
      Repeater {
        model: 3
        Rectangle {
          width: 3.5
          height: 3.5
          radius: 1.75
          color: root.isProcessing ? "#facc15" : (Style.colors.accent || "#38bdf8")
          SequentialAnimation on opacity {
            loops: Animation.Infinite
            running: root.isListening || root.isProcessing
            PauseAnimation { duration: index * (root.isProcessing ? 120 : 180) }
            NumberAnimation { from: 0.2; to: 1.0; duration: (root.isProcessing ? 250 : 350); easing.type: Easing.InOutQuad }
            NumberAnimation { from: 1.0; to: 0.2; duration: (root.isProcessing ? 250 : 350); easing.type: Easing.InOutQuad }
            PauseAnimation { duration: (2 - index) * (root.isProcessing ? 120 : 180) }
          }
          SequentialAnimation on scale {
            loops: Animation.Infinite
            running: root.isListening || root.isProcessing
            PauseAnimation { duration: index * (root.isProcessing ? 120 : 180) }
            NumberAnimation { from: 0.7; to: 1.3; duration: (root.isProcessing ? 250 : 350); easing.type: Easing.InOutQuad }
            NumberAnimation { from: 1.3; to: 0.7; duration: (root.isProcessing ? 250 : 350); easing.type: Easing.InOutQuad }
            PauseAnimation { duration: (2 - index) * (root.isProcessing ? 120 : 180) }
          }
        }
      }
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    iconComponent: (root.isListening || root.isProcessing) ? threeDotsComponent : null
    text: (root.isListening || root.isProcessing) ? "" : "󰍭"
    active: root.isListening || root.isProcessing
    useActiveColor: true
    activeColor: root.isProcessing ? "#facc15" : (Style.colors.accent || "#38bdf8")
    tooltipText: {
      if (root.isListening) return "Max: Listening (Speak now)..."
      if (root.isProcessing) return "Max: Processing (Thinking & Responding)..."
      return "Max Voice Assistant (Muted | Left: Speak | Right: Continuous | Super+A)"
    }

    onPressed: function(mouseButton) {
      if (mouseButton === Qt.RightButton) {
        Quickshell.execDetached(["omarchy-assistant", "continuous", "toggle"])
      } else if (mouseButton === Qt.MiddleButton) {
        Quickshell.execDetached(["omarchy-assistant", "meeting", "start"])
      } else {
        Quickshell.execDetached(["omarchy-assistant", "listen"])
      }
    }
  }
}
