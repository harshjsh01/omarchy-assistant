import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "harshjsh01.assistant"
  ipcTarget: "harshjsh01.assistant"
  manageIpc: false
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  property string currentState: "idle"
  property bool continuousMode: false
  property string currentTranscript: ""
  property string currentAction: ""
  property bool ttsEnabled: true
  property string sttEngine: "WhisperCppEngine"

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.4)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property bool isListening: currentState === "listening"
  readonly property bool isProcessing: currentState === "processing" || currentState === "executing" || currentState === "speaking"

  function alpha(c, a) { return Qt.rgba(c.r, c.g, c.b, a) }

  function loadState(raw) {
    try {
      if (!raw || raw.trim() === "") return
      var data = JSON.parse(raw)
      if (data.state !== undefined) root.currentState = data.state
      if (data.continuous_mode !== undefined) root.continuousMode = data.continuous_mode
      if (data.transcript !== undefined) root.currentTranscript = data.transcript
      if (data.last_action !== undefined) root.currentAction = data.last_action
      if (data.tts_enabled !== undefined) root.ttsEnabled = data.tts_enabled
      if (data.stt_engine !== undefined) root.sttEngine = data.stt_engine
    } catch (err) {}
  }

  FileView {
    id: stateWatcher
    path: "/tmp/omarchy-assistant-state.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.loadState(text())
    onFileChanged: reload()
  }

  IpcHandler {
    target: "harshjsh01.assistant"
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function trigger(): void { Quickshell.execDetached(["omarchy-assistant", "listen"]) }
  }

  IpcHandler {
    target: "assistant"
    function updateState(payloadJson: string): string {
      root.loadState(payloadJson)
      return "ok"
    }
    function state(): string { return root.currentState }
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
  }

  // Bar icon 3-dots animation component
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
    text: (root.isListening || root.isProcessing) ? "" : (root.continuousMode ? "󰍬" : "󰍭")
    active: root.isListening || root.isProcessing || root.opened || root.continuousMode
    useActiveColor: true
    activeColor: root.isProcessing ? "#facc15" : (root.continuousMode ? "#4ade80" : (Style.colors.accent || "#38bdf8"))
    tooltipText: {
      if (root.isListening) return "Max: Listening (Speak now)..."
      if (root.isProcessing) return "Max: Thinking & Speaking..."
      if (root.currentState === "continuous_standby" || root.continuousMode) return "Max: Continuous Standby (Say 'Hey Max' or 'Are you alive?')"
      return "Max Assistant (Click for Dashboard | Right-Click: Continuous Mode)"
    }

    onPressed: function(mouseButton) {
      if (mouseButton === Qt.RightButton) {
        Quickshell.execDetached(["omarchy-assistant", "continuous", "toggle"])
      } else if (mouseButton === Qt.MiddleButton) {
        Quickshell.execDetached(["omarchy-assistant", "meeting", "start"])
      } else {
        root.toggle()
      }
    }
  }

  // Native Dropdown Panel
  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(420))
    contentHeight: Math.min(Style.space(620), contentCol.implicitHeight + Style.space(24))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      Keys.onEscapePressed: root.close()
    }

    Flickable {
      anchors.fill: parent
      contentWidth: width
      contentHeight: contentCol.implicitHeight + Style.space(16)
      clip: true
      boundsBehavior: Flickable.StopAtBounds
      ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

      Column {
        id: contentCol
        width: parent.width - Style.space(20)
        anchors.horizontalCenter: parent.horizontalCenter
        topPadding: Style.space(10)
        spacing: Style.space(12)

        // 1. Header Section
        Item {
          width: parent.width
          implicitHeight: Math.max(headerLeft.implicitHeight, headerRight.implicitHeight)

          Row {
            id: headerLeft
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(10)

            Rectangle {
              width: Style.space(36)
              height: Style.space(36)
              radius: Style.space(18)
              color: root.alpha(root.isProcessing ? "#facc15" : (root.isListening ? Color.accent : Color.foreground), 0.12)
              anchors.verticalCenter: parent.verticalCenter

              Text {
                anchors.centerIn: parent
                text: "󰚩"
                color: root.isProcessing ? "#facc15" : (root.isListening ? Color.accent : Color.foreground)
                font.family: root.fontFamily
                font.pixelSize: Style.space(20)
              }
            }

            Column {
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(2)

              Text {
                text: "Max Assistant"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.title
                font.bold: true
              }

              Row {
                spacing: Style.space(6)
                Rectangle {
                  width: Style.space(8)
                  height: Style.space(8)
                  radius: Style.space(4)
                  color: root.isProcessing ? "#facc15" : (root.isListening ? "#38bdf8" : (root.continuousMode ? "#4ade80" : root.dim))
                  anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                  text: {
                    if (root.isListening) return "Listening to voice..."
                    if (root.isProcessing) return "Thinking (Gemini 3.8 Flash)..."
                    if (root.currentState === "continuous_standby" || root.continuousMode) return "Continuous Standby (Say 'Hey Max')"
                    return "Ready • Super+A"
                  }
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }
            }
          }

          Row {
            id: headerRight
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(6)

            Button {
              text: "󰦒 New Chat"
              fontFamily: root.fontFamily
              fontSize: Style.font.caption
              onClicked: {
                Quickshell.execDetached(["omarchy-assistant", "exec", "start new chat"])
              }
            }

            Button {
              text: "󰅖"
              fontFamily: root.fontFamily
              fontSize: Style.font.caption
              onClicked: root.close()
            }
          }
        }

        // Separator
        Rectangle {
          width: parent.width
          height: 1
          color: root.alpha(Color.foreground, 0.08)
        }

        // 2. Interactive Voice Controls Row
        RowLayout {
          width: parent.width
          spacing: Style.space(8)

          Button {
            Layout.fillWidth: true
            text: root.isListening ? "󰍬 Listening..." : "󰍬 Push to Talk"
            fontFamily: root.fontFamily
            fontSize: Style.font.body
            active: root.isListening
            onClicked: {
              Quickshell.execDetached(["omarchy-assistant", "listen"])
            }
          }

          Button {
            Layout.fillWidth: true
            text: root.continuousMode ? "󰓎 Continuous: ON" : "󰓎 Continuous: OFF"
            fontFamily: root.fontFamily
            fontSize: Style.font.body
            active: root.continuousMode
            onClicked: {
              Quickshell.execDetached(["omarchy-assistant", "continuous", "toggle"])
            }
          }
        }

        // 3. Quick Chat Input Box (Dynamic Gemini Chat)
        Rectangle {
          width: parent.width
          height: Style.space(42)
          radius: Style.cornerRadius
          color: root.alpha(Color.foreground, 0.06)
          border.width: 1
          border.color: chatInput.activeFocus ? Color.accent : root.alpha(Color.foreground, 0.12)

          Row {
            anchors.fill: parent
            anchors.leftMargin: Style.space(12)
            anchors.rightMargin: Style.space(8)
            spacing: Style.space(8)

            TextInput {
              id: chatInput
              width: parent.width - Style.space(40)
              anchors.verticalCenter: parent.verticalCenter
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              selectByMouse: true
              clip: true

              Text {
                text: "Ask Max or give a command..."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                visible: !chatInput.text && !chatInput.activeFocus
                anchors.verticalCenter: parent.verticalCenter
              }

              Keys.onReturnPressed: {
                if (chatInput.text.trim() !== "") {
                  var cmd = chatInput.text.trim()
                  chatInput.text = ""
                  Quickshell.execDetached(["omarchy-assistant", "exec", cmd])
                }
              }
            }

            Button {
              anchors.verticalCenter: parent.verticalCenter
              text: "󰒭"
              fontFamily: root.fontFamily
              fontSize: Style.font.body
              onClicked: {
                if (chatInput.text.trim() !== "") {
                  var cmd = chatInput.text.trim()
                  chatInput.text = ""
                  Quickshell.execDetached(["omarchy-assistant", "exec", cmd])
                }
              }
            }
          }
        }

        // 4. Live Activity / Response Card
        Rectangle {
          width: parent.width
          implicitHeight: activityCol.implicitHeight + Style.space(16)
          radius: Style.cornerRadius
          color: root.alpha(Color.foreground, 0.04)
          border.width: 1
          border.color: root.alpha(Color.foreground, 0.08)

          Column {
            id: activityCol
            width: parent.width - Style.space(20)
            anchors.centerIn: parent
            spacing: Style.space(6)

            Row {
              spacing: Style.space(6)
              Text {
                text: "󰄬 Latest Dialogue"
                color: Color.accent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }
            }

            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              text: root.currentTranscript ? ("\"" + root.currentTranscript + "\"") : "No recent speech."
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
            }

            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              visible: root.currentAction !== ""
              text: "Max: " + root.currentAction
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
        }

        // 5. System Controls & Features
        RowLayout {
          width: parent.width
          spacing: Style.space(8)

          Button {
            Layout.fillWidth: true
            text: root.currentState === "meeting_recording" ? "󰻃 Stop Meeting" : "󰻃 Record Meeting"
            fontFamily: root.fontFamily
            fontSize: Style.font.caption
            active: root.currentState === "meeting_recording"
            onClicked: {
              if (root.currentState === "meeting_recording") {
                Quickshell.execDetached(["omarchy-assistant", "meeting", "stop"])
              } else {
                Quickshell.execDetached(["omarchy-assistant", "meeting", "start"])
              }
            }
          }

          Button {
            Layout.fillWidth: true
            text: "󰈙 Transcripts"
            fontFamily: root.fontFamily
            fontSize: Style.font.caption
            onClicked: {
              Quickshell.execDetached(["xdg-open", Quickshell.env("HOME") + "/Documents/Omarchy-Transcripts"])
            }
          }

          Button {
            Layout.fillWidth: true
            text: "󰉋 Chat Workspace"
            fontFamily: root.fontFamily
            fontSize: Style.font.caption
            onClicked: {
              Quickshell.execDetached(["xdg-open", Quickshell.env("HOME") + "/Work/chat"])
            }
          }
        }

        // 6. Settings Row
        Rectangle {
          width: parent.width
          implicitHeight: settingsCol.implicitHeight + Style.space(16)
          radius: Style.cornerRadius
          color: root.alpha(Color.foreground, 0.03)

          Column {
            id: settingsCol
            width: parent.width - Style.space(16)
            anchors.centerIn: parent
            spacing: Style.space(10)

            Row {
              width: parent.width
              Item {
                width: parent.width - Style.space(50)
                height: Style.space(24)
                anchors.verticalCenter: parent.verticalCenter
                Column {
                  anchors.verticalCenter: parent.verticalCenter
                  Text {
                    text: "Voice Feedback (Speaker)"
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    font.bold: true
                  }
                  Text {
                    text: "Speak aloud via PipeWire audio sink"
                    color: root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.space(10)
                  }
                }
              }

              ToggleSwitch {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                checked: root.ttsEnabled
                onToggled: {
                  Quickshell.execDetached(["python3", "-c", "import socket, json; s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.connect('/tmp/omarchy-assistant.sock'); s.sendall(json.dumps({'action': 'toggle_tts'}).encode()); s.close()"])
                }
              }
            }

            Rectangle {
              width: parent.width
              height: 1
              color: root.alpha(Color.foreground, 0.05)
            }

            Row {
              spacing: Style.space(12)
              Text {
                text: "AI: Google AI Pro (Gemini 3.8 Flash)"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.space(11)
              }
              Text {
                text: "•"
                color: root.dim
                font.pixelSize: Style.space(11)
              }
              Text {
                text: "STT: Whisper C++"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.space(11)
              }
            }
          }
        }

      }
    }
  }
}
