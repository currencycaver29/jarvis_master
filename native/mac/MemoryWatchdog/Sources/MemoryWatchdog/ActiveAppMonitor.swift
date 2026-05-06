import AppKit
import Foundation

/// Watches NSWorkspace app-activation events.
/// Sends app name + bundle ID to ephemeral tier on each switch.
final class ActiveAppMonitor {

    private var observer: NSObjectProtocol?

    func start() {
        observer = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification,
            object: nil,
            queue: .main
        ) { [weak self] note in
            self?.handleActivation(note)
        }
        print("[ActiveAppMonitor] Watching app switches")
    }

    func stop() {
        if let obs = observer {
            NSWorkspace.shared.notificationCenter.removeObserver(obs)
            observer = nil
        }
    }

    private func handleActivation(_ notification: Notification) {
        guard let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey]
                            as? NSRunningApplication
        else { return }

        let name       = app.localizedName ?? "Unknown"
        let bundleId   = app.bundleIdentifier ?? "unknown"

        // Skip Finder and this process
        guard bundleId != "com.apple.finder",
              bundleId != Bundle.main.bundleIdentifier
        else { return }

        let content = "App switch: \(name) (\(bundleId))"
        MemoryClient.sendEphemeral(content: content, source: "app_switch", appName: name)
    }
}
