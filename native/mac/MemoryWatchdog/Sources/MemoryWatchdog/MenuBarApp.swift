import AppKit
import Foundation

/// Menu bar presence for SHAIL Memory Watchdog.
/// Shows live watcher status, capture counter, and control actions.
final class MenuBarApp: NSObject, NSApplicationDelegate {

    private var statusItem: NSStatusItem?
    private var menu: NSMenu?

    // Shared state from running watchers (set externally)
    var captureCount: Int = 0
    var lastCapturedTitle: String = "—"
    private var recentApps: [String] = []

    // Menu item references for live updates
    private var statusMenuItem:    NSMenuItem?
    private var captureMenuItem:   NSMenuItem?
    private var fsMenuItem:        NSMenuItem?
    private var clipMenuItem:      NSMenuItem?
    private var appMenuItem:       NSMenuItem?
    private var updateTimer:       Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        _ = AXTextScraper.ensureAccessibilityTrust(prompt: true)
        buildStatusItem()
        startUpdateTimer()
    }

    func applicationWillTerminate(_ notification: Notification) {
        // Kill Ollama when SHAIL quits so it doesn't linger in the background.
        let task = Process()
        task.launchPath = "/usr/bin/pkill"
        task.arguments = ["-f", "ollama"]
        try? task.run()
        task.waitUntilExit()
    }

    // MARK: - Build

    private func buildStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)

        if let button = statusItem?.button {
            button.image = NSImage(systemSymbolName: "brain.fill", accessibilityDescription: "SHAIL Memory")
            button.toolTip = "SHAIL Memory Watchdog — active"
        }

        menu = NSMenu()
        rebuildMenu()
        statusItem?.menu = menu
    }

    private func rebuildMenu() {
        guard let menu else { return }
        menu.removeAllItems()

        // ── Header ────────────────────────────────────────────────────
        let headerItem = NSMenuItem()
        headerItem.view = makeHeaderView()
        menu.addItem(headerItem)
        menu.addItem(.separator())

        // ── Watcher status ────────────────────────────────────────────
        let fsItem = NSMenuItem(title: "● FS Events  (Documents/Desktop/Downloads)",
                                action: nil, keyEquivalent: "")
        fsItem.isEnabled = false
        fsItem.image = NSImage(systemSymbolName: "folder.fill", accessibilityDescription: nil)
        fsMenuItem = fsItem
        menu.addItem(fsItem)

        let clipItem = NSMenuItem(title: "● Clipboard  (polling every 2 s)",
                                  action: nil, keyEquivalent: "")
        clipItem.isEnabled = false
        clipMenuItem = clipItem
        menu.addItem(clipItem)

        let appItem = NSMenuItem(title: "● App Monitor  (NSWorkspace)",
                                 action: nil, keyEquivalent: "")
        appItem.isEnabled = false
        appMenuItem = appItem
        menu.addItem(appItem)

        menu.addItem(.separator())

        // ── Capture stats ─────────────────────────────────────────────
        let captureItem = NSMenuItem(title: "Captures this session: 0",
                                     action: nil, keyEquivalent: "")
        captureItem.isEnabled = false
        captureMenuItem = captureItem
        menu.addItem(captureItem)

        menu.addItem(.separator())

        // ── Actions ───────────────────────────────────────────────────
        menu.addItem(NSMenuItem(
            title: "Save clipboard to memory",
            action: #selector(saveClipboard),
            keyEquivalent: "s"
        ))

        menu.addItem(NSMenuItem(
            title: "Save desktop context to memory",
            action: #selector(saveDesktopContext),
            keyEquivalent: "d"
        ))

        menu.addItem(NSMenuItem(
            title: "Open SHAIL dashboard…",
            action: #selector(openDashboard),
            keyEquivalent: ""
        ))

        menu.addItem(NSMenuItem(
            title: "View backend log…",
            action: #selector(openBackendLog),
            keyEquivalent: "l"
        ))

        menu.addItem(.separator())

        // Backend status
        let backendItem = NSMenuItem(title: "Checking backend…", action: nil, keyEquivalent: "")
        backendItem.isEnabled = false
        statusMenuItem = backendItem
        menu.addItem(backendItem)

        menu.addItem(.separator())

        menu.addItem(NSMenuItem(
            title: "Quit Memory Watchdog",
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: "q"
        ))
    }

    // MARK: - Header view (rich NSView in menu)

    private func makeHeaderView() -> NSView {
        let container = NSView(frame: NSRect(x: 0, y: 0, width: 280, height: 44))

        let iconView = NSImageView(frame: NSRect(x: 12, y: 10, width: 24, height: 24))
        iconView.image = NSImage(systemSymbolName: "brain.fill", accessibilityDescription: nil)
        iconView.contentTintColor = .controlAccentColor
        container.addSubview(iconView)

        let titleField = NSTextField(labelWithString: "SHAIL Memory Watchdog")
        titleField.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
        titleField.textColor = .labelColor
        titleField.frame = NSRect(x: 44, y: 24, width: 220, height: 16)
        container.addSubview(titleField)

        let subtitleField = NSTextField(labelWithString: "Running — watching 3 sources")
        subtitleField.font = NSFont.systemFont(ofSize: 11)
        subtitleField.textColor = .secondaryLabelColor
        subtitleField.frame = NSRect(x: 44, y: 8, width: 220, height: 14)
        container.addSubview(subtitleField)

        return container
    }

    // MARK: - Live update timer

    private func startUpdateTimer() {
        updateTimer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { [weak self] _ in
            self?.updateMenuItems()
            self?.checkBackend()
        }
    }

    private func updateMenuItems() {
        captureMenuItem?.title = "Captures this session: \(captureCount)"
        if captureCount > 0 {
            captureMenuItem?.title += "  (last: \(lastCapturedTitle))"
        }
    }

    private func checkBackend() {
        guard let url = URL(string: "http://localhost:8000/health") else { return }
        URLSession.shared.dataTask(with: url) { [weak self] _, resp, _ in
            DispatchQueue.main.async {
                let ok = (resp as? HTTPURLResponse).map { (200...299).contains($0.statusCode) } ?? false
                self?.statusMenuItem?.title = ok
                    ? "✓ Backend connected (localhost:8000)"
                    : "✗ Backend offline — start services"
                self?.statusMenuItem?.image = NSImage(
                    systemSymbolName: ok ? "checkmark.circle" : "xmark.circle",
                    accessibilityDescription: nil
                )
            }
        }.resume()
    }

    // Increment capture counter (called by watchers)
    func recordCapture(title: String) {
        DispatchQueue.main.async {
            self.captureCount += 1
            self.lastCapturedTitle = title
        }
    }

    // Track recent app switches for context snapshots
    func recordAppSwitch(name: String) {
        DispatchQueue.main.async {
            self.recentApps.append(name)
            if self.recentApps.count > 10 { self.recentApps.removeFirst() }
        }
    }

    // MARK: - Actions

    @objc private func saveClipboard() {
        guard let text = NSPasteboard.general.string(forType: .string), !text.isEmpty else { return }
        MemoryClient.promoteToImportant(content: text, title: "Clipboard save \(Date())", source: "clipboard")
        recordCapture(title: "Clipboard save")
    }

    @objc private func openBackendLog() {
        // Try common repo roots — first hit wins
        let candidates = [
            NSHomeDirectory() + "/jarvis_master/logs/shail_api.log",
            NSHomeDirectory() + "/Documents/jarvis_master/logs/shail_api.log",
        ]
        for path in candidates where FileManager.default.fileExists(atPath: path) {
            NSWorkspace.shared.open(URL(fileURLWithPath: path))
            return
        }
        // Fallback: open the logs directory
        let dir = NSHomeDirectory() + "/jarvis_master/logs"
        if FileManager.default.fileExists(atPath: dir) {
            NSWorkspace.shared.open(URL(fileURLWithPath: dir))
        }
    }

    /// Sprint 1: surfaced by MemoryClient when no API key is present at
    /// ~/.shail/api_key. Without a key all captures would land in the `local`
    /// namespace and be invisible to the dashboard (Bearer-only). Tell the
    /// user to sign in via ShailUI.
    func showSignInGate() {
        let alert = NSAlert()
        alert.messageText = "Sign in to SHAIL"
        alert.informativeText = "MemoryWatchdog won't capture memories until you sign in. Open ShailUI and complete sign-in to enable capture."
        alert.addButton(withTitle: "Open ShailUI")
        alert.addButton(withTitle: "Cancel")
        if alert.runModal() == .alertFirstButtonReturn {
            openDashboard()
        }
    }

    @objc private func openDashboard() {
        // 1. Use shail:// URL scheme — macOS routes it to ShailUI if it's registered.
        //    If ShailUI isn't running, macOS will launch it first, then send the URL.
        if let shailURL = URL(string: "shail://dashboard") {
            NSWorkspace.shared.open(shailURL)
            return
        }

        // 2. Bring running ShailUI to front by bundle ID (fallback for dev builds)
        let knownBundleIds = ["com.shail.ShailUI", "com.reyhan.ShailUI", "ShailUI"]
        for bid in knownBundleIds {
            if let app = NSRunningApplication.runningApplications(withBundleIdentifier: bid).first {
                app.activate(options: .activateIgnoringOtherApps)
                return
            }
        }

        // 3. Try known binary / .app paths
        let appCandidates = [
            "/Applications/SHAIL.app",
            NSHomeDirectory() + "/Applications/SHAIL.app",
            NSHomeDirectory() + "/jarvis_master/apps/mac/ShailUI/DerivedData/ShailUI/Build/Products/Debug/ShailUI",
            NSHomeDirectory() + "/jarvis_master/apps/mac/ShailUI/.build/release/ShailUI",
        ]
        for path in appCandidates where FileManager.default.fileExists(atPath: path) {
            let task = Process()
            task.launchPath = path
            try? task.run()
            return
        }
    }

    @objc private func saveDesktopContext() {
        let activeApp = NSWorkspace.shared.frontmostApplication?.localizedName ?? "Unknown"
        let clip = NSPasteboard.general.string(forType: .string) ?? ""
        let clipPreview = clip.isEmpty ? "" : String(clip.prefix(400))
        let recent = recentApps.suffix(5)
        let timeStr = DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .medium)

        // Pull window title + scraped Accessibility text. Falls back to
        // app-name + clipboard if AX is denied.
        if !AXTextScraper.ensureAccessibilityTrust(prompt: false) {
            promptAccessibilityAccess()
            // Still save what we have — better than nothing.
        }
        let scrape = AXTextScraper.scrapeFrontmost()
        let windowTitle = scrape?.windowTitle ?? ""
        let scraped     = scrape?.text ?? ""

        // Compressed JSON-shaped payload. ~2 KB typical, capped at 8 KB by scraper.
        var blob: [String: Any] = [
            "active_app":   activeApp,
            "window_title": windowTitle,
            "scraped_text": scraped,
            "clipboard":    clipPreview,
            "recent_apps":  Array(recent),
            "captured_ts":  Date().timeIntervalSince1970,
        ]
        let title = windowTitle.isEmpty
            ? "\(activeApp) — \(timeStr)"
            : "\(activeApp) — \(windowTitle)"

        if let data = try? JSONSerialization.data(withJSONObject: blob, options: [.sortedKeys]),
           let json = String(data: data, encoding: .utf8) {
            MemoryClient.sendEphemeral(
                content: json,
                source: "macos_screen",
                appName: activeApp
            )
            // Also promote to important so it survives TTL — text-only, not a screenshot.
            MemoryClient.promoteToImportant(content: json, title: title, source: "macos_screen")
        } else {
            // Fallback: plain text
            let content = "Active: \(activeApp)\nWindow: \(windowTitle)\nClipboard: \(clipPreview)\n\n\(scraped)"
            MemoryClient.promoteToImportant(content: content, title: title, source: "macos_screen")
        }
        recordCapture(title: title)
        _ = blob.removeValue(forKey: "scraped_text")  // silence unused-blob warning
    }

    private func promptAccessibilityAccess() {
        let alert = NSAlert()
        alert.messageText = "Grant Accessibility access"
        alert.informativeText = "SHAIL Memory Watchdog needs Accessibility permission to read window content. Open System Settings → Privacy & Security → Accessibility and enable MemoryWatchdog."
        alert.addButton(withTitle: "Open System Settings")
        alert.addButton(withTitle: "Cancel")
        if alert.runModal() == .alertFirstButtonReturn {
            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") {
                NSWorkspace.shared.open(url)
            }
        }
    }
}
