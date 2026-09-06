import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Item {
  id: root

  property string currentState: "idle"
  property string currentTranscript: ""
  property string currentAction: ""

  Timer {
    id: hideTimer
    interval: 3500
    repeat: false
    onTriggered: {
      root.currentState = "idle"
      root.currentTranscript = ""
      root.currentAction = ""
    }
  }

  Overlay {
    id: overlay
    assistantState: root.currentState
    transcript: root.currentTranscript
    actionText: root.currentAction
  }

  IpcHandler {
    target: "assistant"

    function updateState(payloadJson: string): string {
      try {
        var data = JSON.parse(payloadJson)
        if (data.state !== undefined) root.currentState = data.state
        if (data.transcript !== undefined) root.currentTranscript = data.transcript
        if (data.action !== undefined) root.currentAction = data.action

        if (root.currentState === "idle") {
          hideTimer.restart()
        } else {
          hideTimer.stop()
        }
        return "ok"
      } catch (err) {
        return "error: " + err
      }
    }

    function trigger(): string {
      root.currentState = "listening"
      Quickshell.execDetached(["omarchy-assistant", "listen"])
      return "triggered"
    }

    function state(): string {
      return root.currentState
    }

    function ping(): string {
      return "pong"
    }
  }
}
