import AppKit
import ApplicationServices
import Foundation

/// Walks the Accessibility tree of the frontmost application and collects
/// visible text from titles, values, and selected text. Output is capped
/// at MAX_CHARS so a runaway window does not blow up memory.
enum AXTextScraper {

    static let MAX_CHARS    = 8_000
    static let MAX_DEPTH    = 6
    static let MAX_CHILDREN = 80

    /// Returns (windowTitle, scrapedText). Returns nil if AX is not authorized
    /// or there is no frontmost app.
    static func scrapeFrontmost() -> (windowTitle: String, text: String)? {
        guard let app = NSWorkspace.shared.frontmostApplication else { return nil }
        let pid = app.processIdentifier
        let appElement = AXUIElementCreateApplication(pid)

        // Frontmost window
        var frontWin: AnyObject?
        AXUIElementCopyAttributeValue(appElement, kAXFocusedWindowAttribute as CFString, &frontWin)
        let windowEl = frontWin as! AXUIElement?
        var title = ""
        if let win = windowEl {
            title = readString(win, kAXTitleAttribute) ?? ""
        }

        var collected: [String] = []
        var seen = Set<String>()
        let root: AXUIElement = windowEl ?? appElement
        walk(root, depth: 0, out: &collected, seen: &seen)

        let joined = collected.joined(separator: "\n")
        let trimmed = joined.count > MAX_CHARS ? String(joined.prefix(MAX_CHARS)) : joined
        return (title, trimmed)
    }

    /// Quick check used at launch — prompts the user to grant Accessibility
    /// access on first run. Returns true if already trusted.
    @discardableResult
    static func ensureAccessibilityTrust(prompt: Bool) -> Bool {
        let key = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        let opts: CFDictionary = [key: prompt] as CFDictionary
        return AXIsProcessTrustedWithOptions(opts)
    }

    // MARK: - Internal

    private static func walk(
        _ el: AXUIElement,
        depth: Int,
        out: inout [String],
        seen: inout Set<String>
    ) {
        if depth > MAX_DEPTH { return }
        if out.joined().count > MAX_CHARS { return }

        for attr in [kAXTitleAttribute, kAXValueAttribute, kAXSelectedTextAttribute, kAXDescriptionAttribute] {
            if let s = readString(el, attr) {
                let stripped = s.trimmingCharacters(in: .whitespacesAndNewlines)
                if stripped.count >= 2 && !seen.contains(stripped) {
                    seen.insert(stripped)
                    out.append(stripped)
                }
            }
        }

        var childrenRef: AnyObject?
        AXUIElementCopyAttributeValue(el, kAXChildrenAttribute as CFString, &childrenRef)
        guard let children = childrenRef as? [AXUIElement] else { return }
        for child in children.prefix(MAX_CHILDREN) {
            walk(child, depth: depth + 1, out: &out, seen: &seen)
        }
    }

    private static func readString(_ el: AXUIElement, _ attr: String) -> String? {
        var ref: AnyObject?
        let res = AXUIElementCopyAttributeValue(el, attr as CFString, &ref)
        if res != .success { return nil }
        return ref as? String
    }
}
