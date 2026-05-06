import AppKit
import Foundation

/// Polls NSPasteboard every 2 seconds. Sends text > 100 chars to ephemeral tier.
final class ClipboardWatcher {

    private var timer: Timer?
    private var lastClipboard: String = ""
    private let minLength = 100

    func start() {
        timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.poll()
        }
        print("[ClipboardWatcher] Polling clipboard every 2s")
    }

    func stop() {
        timer?.invalidate()
        timer = nil
    }

    private func poll() {
        guard let text = NSPasteboard.general.string(forType: .string),
              text.count >= minLength,
              text != lastClipboard
        else { return }

        lastClipboard = text
        MemoryClient.sendEphemeral(content: text, source: "clipboard")
    }
}
