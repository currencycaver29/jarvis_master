import Foundation

/// Heuristic importance scorer — returns 0.0–1.0.
/// threshold: 0.5 → ephemeral; 0.75+ → auto-promote to important
enum ImportanceScorer {

    static let ephemeralThreshold: Float = 0.5
    static let importantThreshold: Float = 0.75

    static func score(path: String, content: String) -> Float {
        var s: Float = 0.0

        // Content richness
        if content.count > 500  { s += 0.3 }
        if content.count > 2000 { s += 0.1 }

        // File type
        let ext = (path as NSString).pathExtension.lowercased()
        if ["pdf", "docx", "doc"].contains(ext) { s += 0.3 }
        if ["md", "txt", "pages"].contains(ext)  { s += 0.1 }

        // Location
        let lower = path.lowercased()
        if lower.contains("/documents") { s += 0.2 }
        if lower.contains("/desktop")   { s += 0.1 }

        // Penalty for tmp / cache / hidden
        if lower.contains("/tmp") || lower.contains("/.") { s -= 0.4 }

        return max(0.0, min(1.0, s))
    }
}
