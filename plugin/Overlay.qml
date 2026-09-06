import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui

PanelWindow {
  id: root

  property string assistantState: "idle" // idle, listening, processing, executing, speaking
  property string transcript: ""
  property string actionText: ""
  property bool showHud: assistantState !== "idle"

  visible: opacity > 0.01
  opacity: showHud ? 1.0 : 0.0
  Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }

  anchors {
    top: true
    bottom: true
    left: true
    right: true
  }
  color: "transparent"
  WlrLayershell.namespace: "omarchy-voice-assistant"
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
  exclusionMode: ExclusionMode.Ignore
  mask: Region {} // Visual-only overlay: clicks pass through

  BorderSurface {
    id: hudCard
    width: Math.max(340, Math.min(650, contentCol.implicitWidth + Style.space(32)))
    height: contentCol.implicitHeight + Style.space(24)
    anchors.horizontalCenter: parent.horizontalCenter
    anchors.bottom: parent.bottom
    anchors.bottomMargin: Style.space(80)
    color: Util.alpha(Color.background, 0.95)
    borderSpec: Border.surfaceSpec("popups", "border", Color.popups.border, Math.max(1, Style.space(2)))
    radius: Style.cornerRadius

    ColumnLayout {
      id: contentCol
      anchors.centerIn: parent
      spacing: Style.space(8)

      // Header row with animated mic / state indicator
      RowLayout {
        Layout.alignment: Qt.AlignHCenter
        spacing: Style.space(8)

        Rectangle {
          width: 10
          height: 10
          radius: 5
          color: {
            if (root.assistantState === "listening") return "#ef4444" // red pulse
            if (root.assistantState === "processing") return "#f59e0b" // amber
            if (root.assistantState === "executing") return "#3b82f6" // blue
            return "#10b981" // green
          }

          SequentialAnimation on opacity {
            running: root.assistantState === "listening"
            loops: Animation.Infinite
            NumberAnimation { from: 1.0; to: 0.3; duration: 600 }
            NumberAnimation { from: 0.3; to: 1.0; duration: 600 }
          }
        }

        Text {
          textFormat: Text.PlainText
          font: Style.font.labelSmall
          color: Color.textSubtle
          text: {
            if (root.assistantState === "listening") return "LISTENING..."
            if (root.assistantState === "processing") return "THINKING..."
            if (root.assistantState === "executing") return "EXECUTING..."
            if (root.assistantState === "speaking") return "SPEAKING..."
            return "READY"
          }
        }
      }

      // Transcript Text
      Text {
        Layout.alignment: Qt.AlignHCenter
        Layout.maximumWidth: 580
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        textFormat: Text.PlainText
        font: Style.font.bodyLarge
        color: Color.text
        text: root.transcript !== "" ? ("“" + root.transcript + "”") : "Speak your command..."
        visible: root.transcript !== "" || root.assistantState === "listening"
      }

      // Executed action or feedback
      Rectangle {
        Layout.alignment: Qt.AlignHCenter
        visible: root.actionText !== ""
        color: Util.alpha(Color.surface, 0.8)
        radius: Style.cornerRadiusSmall
        implicitWidth: actionLabel.implicitWidth + Style.space(16)
        implicitHeight: actionLabel.implicitHeight + Style.space(8)

        Text {
          id: actionLabel
          anchors.centerIn: parent
          textFormat: Text.PlainText
          font: Style.font.labelMedium
          color: Color.primary
          text: root.actionText
        }
      }
    }
  }
}
