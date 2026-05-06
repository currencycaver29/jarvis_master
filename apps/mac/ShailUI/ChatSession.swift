import Foundation
import AppKit

// MARK: - Chat Session model

struct ChatSession: Identifiable, Codable {
    var id: String = UUID().uuidString
    var title: String
    var messages: [ChatMessage]
    var createdAt: Date = Date()
    var updatedAt: Date = Date()

    /// Auto-title from first user message
    static func autoTitle(from messages: [ChatMessage]) -> String {
        let first = messages.first(where: { $0.role == .user })?.text ?? "Untitled"
        let trimmed = first.trimmingCharacters(in: .whitespacesAndNewlines)
        let words = trimmed.components(separatedBy: .whitespaces).prefix(6).joined(separator: " ")
        return words.isEmpty ? "Chat" : words
    }
}

// MARK: - Chat Store

final class ChatStore: ObservableObject {
    static let shared = ChatStore()

    @Published private(set) var sessions: [ChatSession] = []

    private let maxSessions = 100
    private let storageURL: URL = {
        let dir = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("SHAIL", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("chat_history.json")
    }()

    private init() { load() }

    // MARK: - CRUD

    @discardableResult
    func upsert(_ session: ChatSession) -> ChatSession {
        var s = session
        s.updatedAt = Date()
        if let idx = sessions.firstIndex(where: { $0.id == s.id }) {
            sessions[idx] = s
        } else {
            sessions.insert(s, at: 0)
        }
        // Trim to cap
        if sessions.count > maxSessions {
            sessions = Array(sessions.prefix(maxSessions))
        }
        save()
        return s
    }

    func delete(id: String) {
        sessions.removeAll { $0.id == id }
        save()
    }

    func rename(id: String, title: String) {
        guard let idx = sessions.firstIndex(where: { $0.id == id }) else { return }
        sessions[idx].title = title
        save()
    }

    // MARK: - Persistence

    private func load() {
        guard let data = try? Data(contentsOf: storageURL),
              let decoded = try? JSONDecoder().decode([ChatSession].self, from: data)
        else { return }
        sessions = decoded
    }

    private func save() {
        guard let data = try? JSONEncoder().encode(sessions) else { return }
        try? data.write(to: storageURL, options: .atomic)
    }

    // MARK: - Export

    /// Returns plain-text representation of a session for sharing
    static func exportText(_ session: ChatSession) -> String {
        let header = """
SHAIL Chat — \(session.title)
Date: \(session.createdAt.formatted(date: .long, time: .shortened))
Messages: \(session.messages.count)
---

"""
        let body = session.messages.map { msg in
            let who = msg.role == .user ? "You" : "SHAIL"
            return "\(who) [\(msg.timestamp.formatted(date: .omitted, time: .shortened))]:\n\(msg.text)"
        }.joined(separator: "\n\n")
        return header + body
    }

    static func exportJSON(_ session: ChatSession) -> Data? {
        let payload: [String: Any] = [
            "id": session.id,
            "title": session.title,
            "createdAt": session.createdAt.iso8601,
            "messages": session.messages.map {
                ["role": $0.role.rawValue, "text": $0.text,
                 "timestamp": $0.timestamp.iso8601]
            }
        ]
        return try? JSONSerialization.data(withJSONObject: payload, options: .prettyPrinted)
    }
}

private extension Date {
    var iso8601: String { ISO8601DateFormatter().string(from: self) }
}
