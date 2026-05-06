import Foundation

struct ServiceStatus: Codable {
    var status: String
    var port: Int?
    var pid: Int?
}

struct SystemStatusResponse: Codable {
    var services: [String: ServiceStatus]
    var tier: String
}

class BackendManager: ObservableObject {
    static let shared = BackendManager()
    @Published var isAvailable: Bool = false
    @Published var serviceStatuses: [String: String] = [:]  // service name → status string
    @Published var tier: String = "free"

    private var timer: Timer?

    private init() {}

    func startMonitoring() {
        check()
        timer = Timer.scheduledTimer(withTimeInterval: 10.0, repeats: true) { [weak self] _ in
            self?.check()
        }
    }

    func stopMonitoring() {
        timer?.invalidate()
        timer = nil
    }

    func check() {
        Task {
            let ok = await Self.ping()
            await MainActor.run { self.isAvailable = ok }
            if ok {
                if let sysStatus = await Self.fetchSystemStatus() {
                    var statuses: [String: String] = [:]
                    for (name, info) in sysStatus.services {
                        statuses[name] = info.status
                    }
                    await MainActor.run {
                        self.serviceStatuses = statuses
                        self.tier = sysStatus.tier
                    }
                }
            }
        }
    }

    private static func ping() async -> Bool {
        guard let url = URL(string: "http://localhost:8000/health") else { return false }
        var req = URLRequest(url: url)
        req.timeoutInterval = 3.0
        guard let (_, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse,
              (200...299).contains(http.statusCode) else { return false }
        return true
    }

    private static func fetchSystemStatus() async -> SystemStatusResponse? {
        guard let url = URL(string: "http://localhost:8000/system/status") else { return nil }
        var req = URLRequest(url: url)
        req.timeoutInterval = 3.0
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse,
              (200...299).contains(http.statusCode) else { return nil }
        return try? JSONDecoder().decode(SystemStatusResponse.self, from: data)
    }
}
