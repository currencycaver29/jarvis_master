import SwiftUI

struct QuickPopupView: View {
    @EnvironmentObject var coordinator: ViewCoordinator
    @EnvironmentObject var backendManager: BackendManager
    @StateObject private var wsClient        = BackendWebSocketClient()
    @StateObject private var desktopManager  = DesktopManager()

    @State private var query:             String  = ""
    @State private var isListening:       Bool    = false
    @State private var nativeHealth:      NativeHealthStatus?
    @State private var pendingPermission: PermissionRequest?
    @State private var showSettings:      Bool    = false
    @State private var showHistory:       Bool    = false

    // MARK: - Ring state

    private var ringState: ShailRingState {
        if let status = wsClient.currentState?.status {
            switch status {
            case "planning", "thinking":    return .thinking
            case "executing", "running":    return .executing
            default: break
            }
        }
        if isListening {
            let grounded = nativeHealth?.capture == "connected"
                        && nativeHealth?.accessibility == "connected"
            return grounded ? .listeningAndSeeing : .listening
        }
        return .idle
    }

    // MARK: - Body

    var body: some View {
        VStack(spacing: 0) {
            header
            contextChips
            ringSection
            if !backendManager.isAvailable {
                Label("Offline — no API key connected", systemImage: "exclamationmark.triangle.fill")
                    .font(ShailTheme.captionFont)
                    .foregroundColor(.orange)
                    .padding(.horizontal, 18)
                    .padding(.bottom, 2)
            }
            searchBar
                .padding(.horizontal, 16)
                .padding(.top, 4)
            statusLine
                .padding(.horizontal, 20)
                .padding(.top, 6)
            Spacer(minLength: 6)
            quickActionButtons
            tipLine
        }
        .frame(minWidth: 360, maxWidth: .infinity)
        .background(ShailTheme.glassBackground())
        .cornerRadius(ShailTheme.cornerRadius)
        .overlay(ShailTheme.glassStroke())
        .gesture(swipeUpGesture)
        .onAppear {
            wsClient.connect()
            backendManager.check()
            checkNativeHealth()
            checkPermissionsAwaiting()
        }
        .onChange(of: wsClient.permissionRequest) { _, newReq in
            if let r = newReq { pendingPermission = r }
        }
        .sheet(item: $pendingPermission) { req in
            PermissionRequestView(
                request: req,
                onApprove: { Task { try? await PermissionService.shared.approve(taskId: req.taskId); pendingPermission = nil } },
                onDeny:    { Task { try? await PermissionService.shared.deny(taskId: req.taskId);    pendingPermission = nil } }
            )
        }
        .sheet(isPresented: $showSettings) { SettingsView() }
        .sheet(isPresented: $showHistory)  { ChatHistoryView() }
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .center) {
            HStack(spacing: 5) {
                Image(systemName: "bolt.fill")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(ShailTheme.primaryGradient)
                Text("SHAIL")
                    .font(.system(size: 13, weight: .bold, design: .rounded))
                    .foregroundColor(.white.opacity(0.9))
            }

            Spacer()

            HStack(spacing: 12) {
                Circle()
                    .fill(wsClient.isConnected ? Color.green : Color.white.opacity(0.25))
                    .frame(width: 6, height: 6)

                // Bird's Eye
                Button { coordinator.showBirdsEye() } label: {
                    Image(systemName: "network")
                        .font(.system(size: 13))
                        .foregroundColor(.white.opacity(0.55))
                }
                .buttonStyle(.plain)
                .help("Bird's Eye View")

                // Chat History
                Button { showHistory = true } label: {
                    ZStack(alignment: .topTrailing) {
                        Image(systemName: "clock.arrow.circlepath")
                            .font(.system(size: 13))
                            .foregroundColor(.white.opacity(0.55))
                        // Badge if there are sessions
                        if !ChatStore.shared.sessions.isEmpty {
                            Circle()
                                .fill(ShailTheme.primaryBlue)
                                .frame(width: 5, height: 5)
                                .offset(x: 3, y: -3)
                        }
                    }
                }
                .buttonStyle(.plain)
                .help("Chat history")

                UserProfileChip()

                Button { showSettings = true } label: {
                    Image(systemName: "gearshape")
                        .font(.system(size: 13))
                        .foregroundColor(.white.opacity(0.55))
                }
                .buttonStyle(.plain)
                .help("Settings")

                Button { coordinator.collapseToLauncher?() } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.white.opacity(0.4))
                }
                .buttonStyle(.plain)
                .help("Collapse")
            }
        }
        .padding(.horizontal, 18)
        .padding(.top, 16)
        .padding(.bottom, 6)
    }

    private var ringSection: some View {
        VStack(spacing: 6) {
            ShailStatusRing(state: ringState)
            Text(ringState.label)
                .font(ShailTheme.captionFont)
                .foregroundColor(.white.opacity(0.5))
                .animation(.easeInOut(duration: 0.2), value: ringState.label)
            Text("Hello Reyhan")
                .font(ShailTheme.titleFont)
                .foregroundColor(.white)
        }
        .padding(.vertical, 14)
    }

    private var searchBar: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass")
                .foregroundColor(.white.opacity(0.4))
                .font(.system(size: 14))

            TextField(
                "",
                text: $query,
                prompt: Text("Ask SHAIL anything…")
                    .foregroundColor(.white.opacity(0.3))
            )
            .textFieldStyle(.plain)
            .font(.system(size: 16, design: .rounded))
            .foregroundColor(.white)
            .onSubmit { submitQuery() }

            if !query.isEmpty {
                Button { submitQuery() } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 22))
                        .foregroundStyle(ShailTheme.primaryGradient)
                }
                .buttonStyle(.plain)
            }

            Button { isListening.toggle() } label: {
                Image(systemName: isListening ? "mic.fill" : "mic")
                    .font(.system(size: 14))
                    .foregroundColor(isListening ? ShailTheme.primaryBlue : .white.opacity(0.4))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .background(Color.white.opacity(0.09))
        .cornerRadius(ShailTheme.innerRadius)
        .overlay(
            RoundedRectangle(cornerRadius: ShailTheme.innerRadius)
                .stroke(
                    query.isEmpty
                        ? Color.white.opacity(0.1)
                        : ShailTheme.primaryBlue.opacity(0.55),
                    lineWidth: 1
                )
        )
    }

    @ViewBuilder
    private var statusLine: some View {
        if !backendManager.isAvailable {
            Label("Backend offline — click ⚡ in menubar to start services",
                  systemImage: "exclamationmark.triangle")
                .font(ShailTheme.captionFont)
                .foregroundColor(.orange.opacity(0.7))
        } else if let h = nativeHealth {
            let ok = h.capture == "connected" && h.accessibility == "connected"
            Label(
                ok ? "Grounded — screen + accessibility active" : "Grounding inactive",
                systemImage: ok ? "checkmark.seal" : "eye.slash"
            )
            .font(ShailTheme.captionFont)
            .foregroundColor(ok ? .white.opacity(0.35) : .orange.opacity(0.65))
        }
    }

    private var tipLine: some View {
        Text("3-finger swipe up → Bird's-Eye  ·  clock → chat history")
            .font(ShailTheme.captionFont)
            .foregroundColor(.white.opacity(0.25))
            .padding(.bottom, 14)
    }

    // MARK: - Context chips

    private var contextChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                if let h = nativeHealth {
                    chipView(label: "SCR", value: h.capture == "connected" ? "ON" : "OFF",
                             active: h.capture == "connected")
                    chipView(label: "ACC", value: h.accessibility == "connected" ? "ON" : "OFF",
                             active: h.accessibility == "connected")
                }
                let sessionCount = ChatStore.shared.sessions.count
                if sessionCount > 0 {
                    chipView(label: "MEM", value: "\(sessionCount) session\(sessionCount == 1 ? "" : "s")",
                             active: true)
                }
                if wsClient.isConnected {
                    chipView(label: "WS", value: "live", active: true, color: .green)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 6)
        }
    }

    private func chipView(label: String, value: String, active: Bool, color: Color = ShailTheme.primaryBlue) -> some View {
        HStack(spacing: 4) {
            Text(label)
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .foregroundColor(.white.opacity(0.45))
            Text(value)
                .font(.system(size: 10, design: .rounded))
                .foregroundColor(active ? color.opacity(0.9) : .white.opacity(0.3))
        }
        .padding(.horizontal, 7).padding(.vertical, 3)
        .background(active ? color.opacity(0.12) : Color.white.opacity(0.04))
        .overlay(RoundedRectangle(cornerRadius: 5).stroke(active ? color.opacity(0.3) : Color.white.opacity(0.08), lineWidth: 1))
        .cornerRadius(5)
    }

    // MARK: - Quick action buttons

    private var quickActionButtons: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                quickActionButton(icon: "arrow.up.right.circle", label: "Open Dashboard", color: .green) {
                    coordinator.showBirdsEye()
                }
                quickActionButton(icon: "eye", label: "Summarize Screen") {
                    let q = "Summarize what's currently on my screen"
                    coordinator.messages.append(ChatMessage(text: q, role: .user))
                    coordinator.pendingQuery = q
                    coordinator.showChatExpanded()
                }
                quickActionButton(icon: "clock.arrow.circlepath", label: "History") {
                    showHistory = true
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 8)
        }
    }

    private func quickActionButton(icon: String, label: String, color: Color = ShailTheme.primaryBlue, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: icon).font(.system(size: 9, weight: .semibold))
                Text(label).font(.system(size: 10, design: .rounded))
            }
            .foregroundColor(color)
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(color.opacity(0.1))
            .overlay(RoundedRectangle(cornerRadius: 7).stroke(color.opacity(0.25), lineWidth: 1))
            .cornerRadius(7)
        }
        .buttonStyle(.plain)
    }

    private var swipeUpGesture: some Gesture {
        DragGesture().onEnded { v in
            if v.translation.height < -80 { coordinator.showBirdsEye() }
        }
    }

    // MARK: - Submit (THE FIX: switch immediately, stream in ChatOverlayView)

    private func submitQuery() {
        guard !query.isEmpty else { return }

        let text = query
        query = ""

        // Offline path
        if !backendManager.isAvailable {
            coordinator.messages.append(ChatMessage(text: text, role: .user))
            coordinator.messages.append(ChatMessage(text: MockDataProvider.offlineReply, role: .assistant))
            coordinator.lastChatResponse = MockDataProvider.offlineReply
            coordinator.showConversationInDashboard = true
            coordinator.showBirdsEye()
            return
        }

        // ── THE FIX ──────────────────────────────────────────────────────────
        // 1. Append user message NOW (visible immediately in chat)
        // 2. Set pendingQuery so ChatOverlayView starts streaming on appear
        // 3. Switch to chat overlay immediately — user sees chat + streaming
        // Do NOT wait for LLM response before switching.
        coordinator.messages.append(ChatMessage(text: text, role: .user))
        coordinator.pendingQuery = text
        coordinator.showChatExpanded()
    }

    // MARK: - Helpers

    private func checkNativeHealth() {
        Task {
            guard let url = URL(string: "http://localhost:8000/health/native") else { return }
            guard let (data, resp) = try? await URLSession.shared.data(from: url),
                  let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode),
                  let decoded = try? JSONDecoder().decode(NativeHealthStatus.self, from: data)
            else { return }
            await MainActor.run { nativeHealth = decoded }
        }
    }

    private func checkPermissionsAwaiting() {
        Task {
            guard let list = try? await PermissionService.shared.fetchAwaitingApproval() else { return }
            await MainActor.run { pendingPermission = list.first }
        }
    }
}
