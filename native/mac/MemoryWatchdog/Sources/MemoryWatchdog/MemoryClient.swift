import AppKit
import Foundation

/// Fire-and-forget HTTP client for the SHAIL local API.
enum MemoryClient {

    static let base = URL(string: "http://localhost:8000")!

    /// Called after every successful POST so the menu bar counter can update.
    static var onCapture: ((String) -> Void)?

    // MARK: - Ephemeral tier

    static func sendEphemeral(
        content: String,
        source: String,
        appName: String? = nil,
        path: String? = nil
    ) {
        var body: [String: Any] = [
            "content": content,
            "source": source,
        ]
        if let app = appName { body["app_name"] = app }
        if let p = path       { body["file_path"] = p  }
        post(path: "/memory/ephemeral", body: body)
    }

    // MARK: - Important tier

    static func promoteToImportant(content: String, title: String, source: String = "manual", path: String? = nil) {
        var body: [String: Any] = [
            "content": content,
            "title":   title,
            "source":  source,
        ]
        if let p = path { body["file_path"] = p }
        post(path: "/memory/important", body: body)
    }

    // MARK: - Path index

    static func sendPathEvent(path: String) {
        post(path: "/path-index/sync", body: ["path": path])
    }

    // MARK: - Private helper

    private static func loadAPIKey() -> String? {
        let path = NSHomeDirectory() + "/.shail/api_key"
        return try? String(contentsOfFile: path, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Tracks whether the user has been nagged about missing API key in this
    /// session. Avoids spamming alerts on every clipboard/FSEvent capture.
    private static var didShowSignInGate = false

    private static func post(path: String, body: [String: Any]) {
        guard let url = URL(string: path, relativeTo: base) else { return }

        // Sprint 1 (ADR-002): refuse capture if no API key. Anonymous writes
        // would land in the `local` namespace which the dashboard (Bearer-only)
        // can never read, causing silent data loss. Surface a one-time alert
        // instead and skip the network request.
        guard let key = loadAPIKey(), !key.isEmpty else {
            print("[MemoryClient] No API key at ~/.shail/api_key — capture skipped (path=\(path)). Sign in to ShailUI.")
            DispatchQueue.main.async {
                if !didShowSignInGate {
                    didShowSignInGate = true
                    (NSApp.delegate as? MenuBarApp)?.showSignInGate()
                }
            }
            return
        }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        req.timeoutInterval = 10
        guard let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        req.httpBody = data

        URLSession.shared.dataTask(with: req) { _, resp, err in
            if let err = err {
                print("[MemoryClient] POST \(path) failed: \(err.localizedDescription)")
            } else if let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode) {
                MemoryClient.onCapture?(path)
            } else if let http = resp as? HTTPURLResponse {
                print("[MemoryClient] POST \(path) → HTTP \(http.statusCode)")
                // 401 means key was deleted/revoked — re-show gate next time.
                if http.statusCode == 401 {
                    DispatchQueue.main.async { didShowSignInGate = false }
                }
            }
        }.resume()
    }
}
