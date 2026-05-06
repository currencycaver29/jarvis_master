import SwiftUI
import AppKit
import AuthenticationServices

// MARK: - Auth state

final class AuthManager: ObservableObject {
    static let shared = AuthManager()

    @Published var isAuthenticated: Bool = false
    @Published var userEmail: String = ""
    @Published var userDisplayName: String = ""
    @Published var avatarInitials: String = ""
    @Published var provider: AuthProvider = .none

    enum AuthProvider: String {
        case none, google, apple
    }

    private let keychainKey = "shail_auth_token"
    private let defaultsPrefix = "shail_user_"

    private init() { restoreSession() }

    // MARK: - Session persistence

    private func restoreSession() {
        guard let email = UserDefaults.standard.string(forKey: defaultsPrefix + "email"),
              !email.isEmpty else { return }
        userEmail       = email
        userDisplayName = UserDefaults.standard.string(forKey: defaultsPrefix + "name") ?? email
        provider        = AuthProvider(rawValue: UserDefaults.standard.string(forKey: defaultsPrefix + "provider") ?? "") ?? .none
        avatarInitials  = makeInitials(userDisplayName)
        isAuthenticated = true
    }

    func signIn(email: String, name: String, provider: AuthProvider) {
        userEmail       = email
        userDisplayName = name.isEmpty ? email : name
        self.provider   = provider
        avatarInitials  = makeInitials(userDisplayName)
        isAuthenticated = true

        UserDefaults.standard.set(email,         forKey: defaultsPrefix + "email")
        UserDefaults.standard.set(userDisplayName, forKey: defaultsPrefix + "name")
        UserDefaults.standard.set(provider.rawValue, forKey: defaultsPrefix + "provider")
    }

    func signOut() {
        isAuthenticated = false
        userEmail       = ""
        userDisplayName = ""
        avatarInitials  = ""
        provider        = .none
        UserDefaults.standard.removeObject(forKey: defaultsPrefix + "email")
        UserDefaults.standard.removeObject(forKey: defaultsPrefix + "name")
        UserDefaults.standard.removeObject(forKey: defaultsPrefix + "provider")
        // Remove shared key file so MemoryWatchdog stops using it
        let keyFile = URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent(".shail/api_key")
        try? FileManager.default.removeItem(at: keyFile)
    }

    /// Write the current API key to ~/.shail/api_key so MemoryWatchdog can read it.
    func persistAPIKey() {
        let key = SettingsManager.shared.settings.apiKey
        guard !key.isEmpty else { return }
        let dir = URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent(".shail")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true, attributes: nil)
        try? key.write(to: dir.appendingPathComponent("api_key"), atomically: true, encoding: .utf8)
    }

    private func makeInitials(_ name: String) -> String {
        let parts = name.components(separatedBy: " ").filter { !$0.isEmpty }
        if parts.count >= 2 {
            return String(parts[0].prefix(1) + parts[1].prefix(1)).uppercased()
        }
        return String(name.prefix(2)).uppercased()
    }
}

// MARK: - Login view

struct LoginView: View {
    @StateObject private var auth = AuthManager.shared
    @State private var isLoading  = false
    @State private var errorMsg: String?
    @State private var showEmailLogin = false

    var body: some View {
        ZStack {
            ShailTheme.glassBackground(material: .hudWindow)

            VStack(spacing: 0) {
                Spacer()

                // Logo
                VStack(spacing: 10) {
                    ZStack {
                        Circle()
                            .fill(ShailTheme.primaryGradient)
                            .frame(width: 64, height: 64)
                        Image(systemName: "bolt.fill")
                            .font(.system(size: 28, weight: .bold))
                            .foregroundColor(.white)
                    }
                    Text("SHAIL")
                        .font(.system(size: 28, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                    Text("Your AI memory layer — sign in to sync")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.5))
                }
                .padding(.bottom, 40)

                // Sign-in buttons
                VStack(spacing: 12) {
                    // Sign in with Apple
                    SignInWithAppleButton(.signIn) { request in
                        request.requestedScopes = [.fullName, .email]
                    } onCompletion: { result in
                        handleAppleAuth(result)
                    }
                    .signInWithAppleButtonStyle(.white)
                    .frame(height: 44)
                    .cornerRadius(11)

                    // Sign in with Google
                    authButton(
                        icon: "globe",
                        label: "Continue with Google",
                        tint: Color(red: 0.26, green: 0.52, blue: 0.96)
                    ) {
                        startGoogleOAuth()
                    }

                    // Divider
                    HStack {
                        Rectangle().fill(Color.white.opacity(0.12)).frame(height: 1)
                        Text("or").font(.caption).foregroundColor(.white.opacity(0.35))
                        Rectangle().fill(Color.white.opacity(0.12)).frame(height: 1)
                    }

                    // Email / API key
                    authButton(
                        icon: "envelope",
                        label: "Sign in with API key",
                        tint: Color.white.opacity(0.6)
                    ) {
                        showEmailLogin = true
                    }
                }
                .frame(maxWidth: 320)

                if let err = errorMsg {
                    Text(err)
                        .font(.caption2)
                        .foregroundColor(.red)
                        .padding(.top, 12)
                }

                if isLoading {
                    ProgressView().padding(.top, 12).tint(.white)
                }

                Spacer()

                Text("Your memory stays local — SHAIL never uploads without permission")
                    .font(.system(size: 10, design: .rounded))
                    .foregroundColor(.white.opacity(0.3))
                    .multilineTextAlignment(.center)
                    .padding(.bottom, 20)
                    .padding(.horizontal, 24)
            }
            .padding(.horizontal, 32)
        }
        .sheet(isPresented: $showEmailLogin) {
            APIKeyLoginView()
        }
    }

    // MARK: - Buttons

    private func authButton(icon: String, label: String, tint: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundColor(tint)
                    .frame(width: 22)
                Text(label)
                    .font(.system(size: 14, design: .rounded).weight(.medium))
                    .foregroundColor(.white)
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(
                ZStack {
                    VisualEffectBlur(material: .hudWindow, blendingMode: .behindWindow)
                    Color.white.opacity(0.07)
                }
            )
            .overlay(RoundedRectangle(cornerRadius: 11).stroke(Color.white.opacity(0.15), lineWidth: 1))
            .cornerRadius(11)
        }
        .buttonStyle(.plain)
    }

    // MARK: - Auth flows

    private func handleAppleAuth(_ result: Result<ASAuthorization, Error>) {
        switch result {
        case .success(let auth):
            guard let cred = auth.credential as? ASAuthorizationAppleIDCredential else {
                errorMsg = "Unexpected credential type from Apple"
                return
            }
            guard let tokenData = cred.identityToken,
                  let identityToken = String(data: tokenData, encoding: .utf8) else {
                errorMsg = "Apple did not return an identity token"
                return
            }
            let name = [cred.fullName?.givenName, cred.fullName?.familyName]
                .compactMap { $0 }.joined(separator: " ")
            isLoading = true
            Task { await verifyAppleToken(identityToken: identityToken, fullName: name) }
        case .failure(let err):
            // ASAuthorizationError 1000 → "Sign In with Apple" capability missing
            // from the app entitlements. Surface that hint to the user.
            errorMsg = "\(err.localizedDescription) — check Sign In with Apple capability is enabled in Xcode."
        }
    }

    private func verifyAppleToken(identityToken: String, fullName: String) async {
        defer { Task { @MainActor in self.isLoading = false } }
        guard let url = URL(string: "http://127.0.0.1:8000/auth/apple") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = ["identity_token": identityToken, "full_name": fullName]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse else { return }
            if !(200...299).contains(http.statusCode) {
                let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
                await MainActor.run {
                    self.errorMsg = "Apple sign-in failed (\(http.statusCode)): \(detail ?? "unknown")"
                }
                return
            }
            guard let json   = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let apiKey = json["api_key"] as? String,
                  let email  = json["email"]   as? String else { return }
            let name = (json["name"] as? String) ?? fullName
            await MainActor.run {
                SettingsManager.shared.settings.apiKey = apiKey
                AuthManager.shared.signIn(email: email, name: name, provider: .apple)
                AuthManager.shared.persistAPIKey()
            }
        } catch {
            await MainActor.run {
                self.errorMsg = "Backend offline — start services first"
            }
        }
    }

    private func startGoogleOAuth() {
        isLoading = true
        let state = UUID().uuidString.lowercased().replacingOccurrences(of: "-", with: "")

        // Pre-flight: read /health to make sure backend is up AND Google
        // OAuth is configured. Avoids opening a browser to a 503 page.
        guard let healthURL = URL(string: "http://127.0.0.1:8000/health"),
              let startURL  = URL(string: "http://127.0.0.1:8000/auth/google/start?state=\(state)")
        else { errorMsg = "Bad URL"; isLoading = false; return }

        Task {
            do {
                let (data, resp) = try await URLSession.shared.data(from: healthURL)
                guard let http = resp as? HTTPURLResponse,
                      (200...299).contains(http.statusCode),
                      let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                    await MainActor.run {
                        self.isLoading = false
                        self.errorMsg = "Backend offline — start services first"
                    }
                    return
                }
                let configured = (json["google_oauth_configured"] as? Bool) ?? false
                if !configured {
                    await MainActor.run {
                        self.isLoading = false
                        self.errorMsg = "Google OAuth not configured — set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env"
                    }
                    return
                }
            } catch {
                await MainActor.run {
                    self.isLoading = false
                    self.errorMsg = "Backend offline — start services first"
                }
                return
            }
            await MainActor.run {
                NSWorkspace.shared.open(startURL)
                self.pollForGoogleToken(state: state)
            }
        }
    }

    private func pollForGoogleToken(state: String) {
        var attempts = 0
        Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { timer in
            attempts += 1
            if attempts > 30 { timer.invalidate(); DispatchQueue.main.async { self.isLoading = false }; return }
            Task {
                guard let url = URL(string: "http://localhost:8000/auth/google/token?state=\(state)"),
                      let (data, resp) = try? await URLSession.shared.data(from: url),
                      let http = resp as? HTTPURLResponse,
                      http.statusCode == 200,   // 204 = not ready yet
                      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let email = json["email"] as? String
                else { return }

                let name   = json["name"] as? String ?? email
                let apiKey = json["api_key"] as? String ?? ""
                timer.invalidate()
                await MainActor.run {
                    self.isLoading = false
                    if !apiKey.isEmpty {
                        SettingsManager.shared.settings.apiKey = apiKey
                        AuthManager.shared.persistAPIKey()
                    }
                    AuthManager.shared.signIn(email: email, name: name, provider: .google)
                }
            }
        }
    }
}

// MARK: - API Key / Email login sheet

struct APIKeyLoginView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var email:  String = ""
    @State private var apiKey: String = ""
    @State private var error:  String?

    var body: some View {
        VStack(spacing: 20) {
            Text("Sign in with API Key")
                .font(ShailTheme.headingFont)

            VStack(alignment: .leading, spacing: 6) {
                Text("Email").font(.caption).foregroundColor(.secondary)
                TextField("you@example.com", text: $email)
                    .textFieldStyle(.roundedBorder)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("API Key").font(.caption).foregroundColor(.secondary)
                SecureField("sk-…", text: $apiKey)
                    .textFieldStyle(.roundedBorder)
            }

            if let err = error {
                Text(err).font(.caption2).foregroundColor(.red)
            }

            HStack {
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Spacer()
                Button("Sign In") { signIn() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(email.isEmpty || apiKey.isEmpty)
            }
        }
        .padding(24)
        .frame(width: 360)
    }

    private func signIn() {
        guard email.contains("@"), apiKey.count > 8 else {
            error = "Enter a valid email and API key"
            return
        }
        SettingsManager.shared.settings.apiKey = apiKey
        AuthManager.shared.signIn(email: email, name: "", provider: .none)
        AuthManager.shared.persistAPIKey()   // Phase 0: write ~/.shail/api_key
        dismiss()
    }
}

// MARK: - User profile chip (shown in top bar when logged in)

struct UserProfileChip: View {
    @StateObject private var auth = AuthManager.shared
    @State private var showPopover = false

    @State private var showLogin = false

    var body: some View {
        if !auth.isAuthenticated {
            Button { showLogin = true } label: {
                HStack(spacing: 5) {
                    Image(systemName: "person.crop.circle")
                        .font(.system(size: 13))
                        .foregroundColor(.white.opacity(0.45))
                    Text("Sign In")
                        .font(.system(size: 11, design: .rounded))
                        .foregroundColor(.white.opacity(0.5))
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.white.opacity(0.08))
                .cornerRadius(12)
            }
            .buttonStyle(.plain)
            .sheet(isPresented: $showLogin) {
                LoginView()
                    .frame(width: 400, height: 580)
            }
        } else if auth.isAuthenticated {
            Button { showPopover.toggle() } label: {
                HStack(spacing: 6) {
                    ZStack {
                        Circle()
                            .fill(ShailTheme.primaryGradient)
                            .frame(width: 22, height: 22)
                        Text(auth.avatarInitials)
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(.white)
                    }
                    Text(auth.userEmail.components(separatedBy: "@").first ?? "")
                        .font(.system(size: 11, design: .rounded))
                        .foregroundColor(.white.opacity(0.7))
                        .lineLimit(1)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.white.opacity(0.08))
                .cornerRadius(12)
            }
            .buttonStyle(.plain)
            .popover(isPresented: $showPopover, arrowEdge: .bottom) {
                profilePopover
            }
        }
    }

    private var profilePopover: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                ZStack {
                    Circle().fill(ShailTheme.primaryGradient).frame(width: 36, height: 36)
                    Text(auth.avatarInitials)
                        .font(.system(size: 14, weight: .bold)).foregroundColor(.white)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(auth.userDisplayName).font(.system(.body, design: .rounded).weight(.semibold))
                    Text(auth.userEmail).font(.caption).foregroundColor(.secondary)
                }
            }

            Divider()

            Label(auth.provider.rawValue.capitalized + " account",
                  systemImage: providerIcon)
                .font(.caption).foregroundColor(.secondary)

            Button("Sign Out") {
                showPopover = false
                auth.signOut()
            }
            .foregroundColor(.red)
            .buttonStyle(.plain)
            .font(.caption)
        }
        .padding(16)
        .frame(width: 220)
    }

    private var providerIcon: String {
        switch auth.provider {
        case .google: return "globe"
        case .apple:  return "apple.logo"
        default:      return "key"
        }
    }
}
