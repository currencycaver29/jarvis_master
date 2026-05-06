import AppKit
import Foundation

// Launch the menu bar app (owns the NSApplication + run loop)
let app      = NSApplication.shared
let delegate = MenuBarApp()
app.delegate = delegate

// Start watchers — pass capture callback so menu counter stays live
let fsWatcher   = FSEventsWatcher()
let clipWatcher = ClipboardWatcher()
let appMonitor  = ActiveAppMonitor()

// Wire capture callback to menu delegate
MemoryClient.onCapture = { title in
    delegate.recordCapture(title: title)
}

// Track recent app switches for the context snapshot action
NSWorkspace.shared.notificationCenter.addObserver(
    forName: NSWorkspace.didActivateApplicationNotification,
    object: nil,
    queue: .main
) { note in
    if let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
       let name = app.localizedName {
        delegate.recordAppSwitch(name: name)
    }
}

fsWatcher.start()
clipWatcher.start()
appMonitor.start()

print("[MemoryWatchdog] Running — watching ~/Documents, ~/Desktop, ~/Downloads + clipboard + app switches")

app.run()
