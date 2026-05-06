import Foundation

struct WebSource: Identifiable, Codable, Hashable {
    let title: String
    let url: String
    let snippet: String

    var id: String { url }
    var host: String {
        URL(string: url)?.host?.replacingOccurrences(of: "www.", with: "") ?? url
    }
}

struct ChatMessage: Identifiable, Codable {
    let id: String
    let text: String
    let role: ChatRole
    let timestamp: Date
    let sources: [WebSource]

    init(
        id: String = UUID().uuidString,
        text: String,
        role: ChatRole,
        timestamp: Date = Date(),
        sources: [WebSource] = []
    ) {
        self.id = id
        self.text = text
        self.role = role
        self.timestamp = timestamp
        self.sources = sources
    }
}

enum ChatRole: String, Codable {
    case user
    case assistant
}
