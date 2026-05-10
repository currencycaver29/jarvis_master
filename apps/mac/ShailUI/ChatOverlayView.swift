import SwiftUI
import AppKit
import UniformTypeIdentifiers

// MARK: - Main chat overlay

struct ChatOverlayView: View {
    @EnvironmentObject var coordinator: ViewCoordinator
    @StateObject private var wsClient = BackendWebSocketClient()

    @State private var inputText:     String = ""
    @State private var isLoading:     Bool   = false
    @State private var showSettings:  Bool   = false
    @State private var streamingMsgId: String? = nil
    @State private var attachedFiles: [AttachedFile] = []
    @State private var _streamingTask: Task<Void, Never>? = nil

    var body: some View {
        VStack(spacing: 0) {
            chatHeader
            chatContextChips
            messageList
            if !attachedFiles.isEmpty { attachmentBar }
            inputBar
        }
        .frame(maxWidth: .infinity)
        .background(ShailTheme.glassBackground())
        .cornerRadius(ShailTheme.cornerRadius)
        .overlay(ShailTheme.glassStroke())
        .sheet(isPresented: $showSettings) { SettingsView() }
        .onAppear {
            wsClient.connect()
            pickUpPendingQuery()
        }
        .onChange(of: coordinator.messages.count) { _, _ in
            // Auto-save session as messages accumulate (non-streaming messages)
            if coordinator.messages.count >= 2 {
                coordinator.saveCurrentSession()
            }
        }
    }

    // MARK: - Header

    private var chatHeader: some View {
        HStack(spacing: 10) {
            // ← Back to quick popup (auto-saves session)
            Button {
                coordinator.saveCurrentSession()
                coordinator.showPopup()
                coordinator.resetToPopupSize?()
            } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.white.opacity(0.55))
            }
            .buttonStyle(.plain)
            .help("Back to quick popup")

            HStack(spacing: 4) {
                Image(systemName: "bolt.fill")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(ShailTheme.primaryGradient)
                Text("SHAIL")
                    .font(.system(size: 13, weight: .bold, design: .rounded))
                    .foregroundColor(.white.opacity(0.9))
            }

            Spacer()

            // New chat
            Button {
                coordinator.startNewChat()
            } label: {
                Image(systemName: "square.and.pencil")
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.45))
            }
            .buttonStyle(.plain)
            .help("New chat")

            // Open Bird's Eye dashboard — chat overlay stays open
            Button {
                coordinator.showBirdsEye()
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "arrow.up.forward.app").font(.system(size: 11))
                    Text("Dashboard").font(.system(size: 11, design: .rounded))
                }
                .foregroundColor(.white.opacity(0.55))
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(Color.white.opacity(0.08))
                .cornerRadius(6)
            }
            .buttonStyle(.plain)
            .help("Open Bird's Eye dashboard")

            Button { showSettings = true } label: {
                Image(systemName: "gearshape").font(.system(size: 13))
                    .foregroundColor(.white.opacity(0.45))
            }
            .buttonStyle(.plain)

            Button { coordinator.collapseToLauncher?() } label: {
                Image(systemName: "xmark").font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.white.opacity(0.35))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16).padding(.vertical, 11)
        .background(Color.white.opacity(0.05))
    }

    // MARK: - Context chips

    private var chatContextChips: some View {
        let sessionCount = ChatStore.shared.sessions.count
        let isLive = wsClient.isConnected
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                if let state = wsClient.currentState {
                    chatChip(label: "AGENT", value: state.status.capitalized, active: true, color: ShailTheme.primaryBlue)
                }
                if sessionCount > 0 {
                    chatChip(label: "MEM", value: "\(sessionCount) sessions", active: true)
                }
                chatChip(label: "WS", value: isLive ? "live" : "offline", active: isLive, color: isLive ? .green : .orange)
                if let sessionId = coordinator.currentSessionId,
                   let session = ChatStore.shared.sessions.first(where: { $0.id == sessionId }) {
                    chatChip(label: "SESSION", value: session.title, active: true, color: .purple)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 5)
        }
        .background(Color.white.opacity(0.03))
        .overlay(Rectangle().frame(height: 1).foregroundColor(.white.opacity(0.06)), alignment: .bottom)
    }

    private func chatChip(label: String, value: String, active: Bool, color: Color = ShailTheme.primaryBlue) -> some View {
        HStack(spacing: 4) {
            Text(label)
                .font(.system(size: 7, weight: .bold, design: .monospaced))
                .foregroundColor(.white.opacity(0.4))
            Text(value)
                .font(.system(size: 9, design: .rounded))
                .foregroundColor(active ? color.opacity(0.85) : .white.opacity(0.3))
                .lineLimit(1)
        }
        .padding(.horizontal, 6).padding(.vertical, 3)
        .background(active ? color.opacity(0.1) : Color.white.opacity(0.04))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(active ? color.opacity(0.25) : Color.white.opacity(0.07), lineWidth: 1))
        .cornerRadius(4)
    }

    // MARK: - Messages

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(coordinator.messages) { msg in
                        MessageBubble(message: msg, isStreaming: msg.id == streamingMsgId)
                            .id(msg.id)
                        // Route taken card after last assistant message
                        if msg.id == coordinator.messages.last?.id,
                           msg.role == .assistant,
                           !isLoading,
                           let state = wsClient.currentState,
                           !state.planSteps.isEmpty {
                            RouteTakenCard(steps: Array(state.planSteps.prefix(4)))
                                .padding(.horizontal, 14)
                                .padding(.top, 2)
                        }
                    }
                    if let taskId = coordinator.activeTaskId {
                        TaskProgressCard(taskId: taskId)
                            .padding(.horizontal, 14).id("task-progress")
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(.horizontal, 14).padding(.vertical, 10)
            }
            .onChange(of: coordinator.messages.count) { _, _ in
                withAnimation(.easeOut(duration: 0.25)) { proxy.scrollTo("bottom", anchor: .bottom) }
            }
            .onChange(of: coordinator.messages.last?.text) { _, _ in
                proxy.scrollTo("bottom", anchor: .bottom)
            }
        }
        .frame(minHeight: 220, maxHeight: .infinity)
    }

    // MARK: - Attachment preview bar

    private var attachmentBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(attachedFiles) { file in
                    HStack(spacing: 4) {
                        Image(systemName: file.icon)
                            .font(.system(size: 11))
                            .foregroundColor(.white.opacity(0.6))
                        Text(file.name)
                            .font(.system(size: 11, design: .rounded))
                            .foregroundColor(.white.opacity(0.75))
                            .lineLimit(1)
                        Button {
                            attachedFiles.removeAll { $0.id == file.id }
                        } label: {
                            Image(systemName: "xmark")
                                .font(.system(size: 9, weight: .bold))
                                .foregroundColor(.white.opacity(0.4))
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(Color.white.opacity(0.08))
                    .cornerRadius(8)
                }
            }
            .padding(.horizontal, 14).padding(.vertical, 6)
        }
        .background(Color.white.opacity(0.04))
        .overlay(Rectangle().frame(height: 1).foregroundColor(.white.opacity(0.07)), alignment: .top)
    }

    // MARK: - Input bar

    private var inputBar: some View {
        HStack(spacing: 10) {
            Button { pickFiles() } label: {
                Image(systemName: "plus")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.white.opacity(0.5))
                    .frame(width: 28, height: 28)
                    .background(Color.white.opacity(0.08))
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
            .help("Attach files or images")

            TextField(
                "",
                text: $inputText,
                prompt: Text("Reply…").foregroundColor(.white.opacity(0.25))
            )
            .textFieldStyle(.plain)
            .font(.system(size: 14, design: .rounded))
            .foregroundColor(.white)
            .onSubmit { sendMessage() }
            .disabled(isLoading)

            if isLoading {
                Button { cancelStreaming() } label: {
                    Image(systemName: "stop.circle.fill")
                        .font(.system(size: 22))
                        .foregroundStyle(Color.red.opacity(0.75))
                }
                .buttonStyle(.plain)
                .help("Stop generation")
            } else {
                Button { sendMessage() } label: {
                    Image(systemName: inputText.isEmpty && attachedFiles.isEmpty ? "mic" : "arrow.up")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(inputText.isEmpty && attachedFiles.isEmpty ? .white.opacity(0.35) : .white)
                        .frame(width: 28, height: 28)
                        .background(
                            (inputText.isEmpty && attachedFiles.isEmpty)
                                ? AnyShapeStyle(Color.white.opacity(0.07))
                                : AnyShapeStyle(ShailTheme.primaryGradient)
                        )
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .disabled(inputText.isEmpty && attachedFiles.isEmpty)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Color.white.opacity(0.06))
        .overlay(Rectangle().frame(height: 1).foregroundColor(.white.opacity(0.07)), alignment: .top)
    }

    // MARK: - File picker

    private func pickFiles() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories    = false
        panel.canChooseFiles          = true
        panel.allowedContentTypes     = [
            .image, .pdf, .plainText, .json,
            UTType(filenameExtension: "csv") ?? .data,
            UTType(filenameExtension: "md")  ?? .plainText,
        ]
        panel.begin { response in
            guard response == .OK else { return }
            DispatchQueue.main.async {
                for url in panel.urls {
                    let ext = url.pathExtension.lowercased()
                    let icon: String
                    if ["png","jpg","jpeg","gif","webp","heic"].contains(ext) { icon = "photo" }
                    else if ext == "pdf" { icon = "doc.richtext" }
                    else { icon = "doc.text" }
                    attachedFiles.append(AttachedFile(url: url, name: url.lastPathComponent, icon: icon))
                }
            }
        }
    }

    // MARK: - Cancel streaming

    private func cancelStreaming() {
        _streamingTask?.cancel()
        _streamingTask = nil
        isLoading = false
        streamingMsgId = nil
    }

    // MARK: - Send / stream

    private func sendMessage() {
        let text  = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        let files = attachedFiles
        guard !text.isEmpty || !files.isEmpty else { return }
        guard !isLoading else { return }

        inputText     = ""
        attachedFiles = []

        var fullText = text
        if !files.isEmpty {
            let names = files.map { "[\($0.name)]" }.joined(separator: ", ")
            fullText  = "\(names)\n\n\(text)"
        }

        coordinator.messages.append(ChatMessage(text: fullText, role: .user))
        startStreaming(text: fullText)
    }

    // MARK: - Pending query pickup (THE FIX)

    /// Called on onAppear. If QuickPopupView queued a pending query, start streaming it immediately.
    /// The user message is already in coordinator.messages — we just start the LLM call.
    private func pickUpPendingQuery() {
        if let pending = coordinator.pendingQuery {
            coordinator.pendingQuery = nil
            // Small delay so the view is fully laid out before we start streaming
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                self.startStreaming(text: pending)
            }
        }
        // No pending query: show whatever is already in coordinator.messages (session restore, etc.)
    }

    /// Core streaming method — can be called by sendMessage (new input) OR pickUpPendingQuery.
    private func startStreaming(text: String) {
        isLoading = true
        coordinator.activeTaskId = nil

        // Insert streaming placeholder (empty, tokens fill it in)
        let placeholder = ChatMessage(text: "", role: .assistant)
        coordinator.messages.append(placeholder)
        streamingMsgId = placeholder.id

        let historySnap: [[String: String]] = coordinator.messages
            .dropLast(2)
            .map { ["role": $0.role == .user ? "user" : "assistant", "content": $0.text] }

        _streamingTask = Task {
            do {
                let result = try await QueryService.shared.submitStreaming(
                    text: text,
                    history: historySnap,
                    onToken: { @MainActor tok in
                        guard let idx = coordinator.messages.firstIndex(where: { $0.id == placeholder.id }) else { return }
                        let cur = coordinator.messages[idx]
                        coordinator.messages[idx] = ChatMessage(
                            id: cur.id, text: cur.text + tok, role: .assistant,
                            timestamp: cur.timestamp, sources: cur.sources
                        )
                    },
                    onSources: { @MainActor srcs in
                        // Sources arrive before tokens — attach them ASAP for inline rendering
                        guard let idx = coordinator.messages.firstIndex(where: { $0.id == placeholder.id }) else { return }
                        let cur = coordinator.messages[idx]
                        coordinator.messages[idx] = ChatMessage(
                            id: cur.id, text: cur.text, role: .assistant,
                            timestamp: cur.timestamp, sources: srcs
                        )
                    }
                )
                await MainActor.run {
                    // Final assembly — make sure text + sources are committed
                    if let idx = coordinator.messages.firstIndex(where: { $0.id == placeholder.id }) {
                        let cur = coordinator.messages[idx]
                        let finalText = cur.text.isEmpty ? result.answer : cur.text
                        coordinator.messages[idx] = ChatMessage(
                            id: placeholder.id, text: finalText, role: .assistant,
                            timestamp: placeholder.timestamp,
                            sources: result.sources.isEmpty ? cur.sources : result.sources
                        )
                    }
                    coordinator.lastChatResponse = result.answer
                    isLoading      = false
                    streamingMsgId = nil
                    coordinator.saveCurrentSession()
                }
            } catch {
                await MainActor.run {
                    coordinator.messages.removeAll { $0.id == placeholder.id }
                    guard !Task.isCancelled else { isLoading = false; streamingMsgId = nil; return }
                    coordinator.messages.append(
                        ChatMessage(text: "⚠️ \(error.localizedDescription)", role: .assistant)
                    )
                    isLoading      = false
                    streamingMsgId = nil
                    coordinator.showOfflineDashboard()
                }
            }
        }
    }
}

// MARK: - Attached file model

struct AttachedFile: Identifiable {
    let id   = UUID()
    let url:  URL
    let name: String
    let icon: String
}

// MARK: - Message bubble

struct MessageBubble: View {
    let message:     ChatMessage
    var isStreaming: Bool = false
    @State private var isHovered = false
    @State private var cursorVisible = true
    @State private var sourcesExpanded = false
    @State private var hoveredSourceId: String?

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            if message.role == .user      { Spacer(minLength: 48) }
            if message.role == .assistant { shailAvatar }

            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 3) {
                ZStack(alignment: message.role == .user ? .topTrailing : .topLeading) {
                    HStack(alignment: .bottom, spacing: 0) {
                        Text(message.text)
                            .font(ShailTheme.bodyFont)
                            .foregroundColor(.white)
                            .padding(.horizontal, 13).padding(.vertical, 9)
                        if isStreaming {
                            Text("▌")
                                .font(ShailTheme.bodyFont)
                                .foregroundColor(cursorVisible ? .white.opacity(0.7) : .clear)
                                .padding(.vertical, 9).padding(.trailing, 6)
                                .onAppear { animateCursor() }
                        }
                    }
                    .background(bubbleBackground)
                    .fixedSize(horizontal: false, vertical: true)

                    if isHovered && !isStreaming {
                        Button {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(message.text, forType: .string)
                        } label: {
                            Image(systemName: "doc.on.doc").font(.system(size: 10))
                                .foregroundColor(.white.opacity(0.8)).padding(5)
                                .background(Circle().fill(Color.black.opacity(0.45)))
                        }
                        .buttonStyle(.plain)
                        .offset(x: message.role == .user ? -6 : 6, y: -6)
                        .transition(.opacity)
                    }
                }

                // Inline citation chips (small link icons under bubble)
                if !message.sources.isEmpty {
                    inlineCitations
                }

                // Expandable source list
                if !message.sources.isEmpty {
                    sourcesToggle
                    if sourcesExpanded { sourcesList }
                }

                Text(message.timestamp.formatted(date: .omitted, time: .shortened))
                    .font(.system(size: 9, design: .rounded))
                    .foregroundColor(.white.opacity(0.25))
                    .padding(.horizontal, 4)
            }

            if message.role == .assistant { Spacer(minLength: 48) }
        }
        .onHover { h in withAnimation(.easeInOut(duration: 0.15)) { isHovered = h } }
    }

    // MARK: - Sources UI

    private var inlineCitations: some View {
        HStack(spacing: 4) {
            ForEach(Array(message.sources.enumerated()), id: \.element.id) { idx, src in
                citationChip(index: idx + 1, source: src)
            }
        }
        .padding(.leading, 8)
        .padding(.top, 2)
    }

    private func citationChip(index: Int, source: WebSource) -> some View {
        Button {
            if let url = URL(string: source.url) { NSWorkspace.shared.open(url) }
        } label: {
            HStack(spacing: 2) {
                Image(systemName: "link")
                    .font(.system(size: 8, weight: .semibold))
                Text("\(index)")
                    .font(.system(size: 9, weight: .semibold, design: .rounded))
            }
            .foregroundColor(.white.opacity(0.75))
            .padding(.horizontal, 5).padding(.vertical, 2)
            .background(
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.white.opacity(hoveredSourceId == source.id ? 0.18 : 0.10))
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.white.opacity(0.15), lineWidth: 1))
            )
        }
        .buttonStyle(.plain)
        .help("\(source.title)\n\(source.host)")
        .onHover { h in hoveredSourceId = h ? source.id : nil }
        .popover(isPresented: .constant(hoveredSourceId == source.id), arrowEdge: .top) {
            sourcePreview(source: source)
        }
    }

    private func sourcePreview(source: WebSource) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Image(systemName: "globe").font(.system(size: 10)).foregroundColor(.secondary)
                Text(source.host).font(.system(size: 10, design: .rounded)).foregroundColor(.secondary)
            }
            Text(source.title).font(.system(.body, design: .rounded).weight(.semibold)).lineLimit(2)
            Text(source.snippet).font(.caption).foregroundColor(.secondary).lineLimit(4)
        }
        .padding(12)
        .frame(width: 280)
    }

    private var sourcesToggle: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.18)) { sourcesExpanded.toggle() }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: sourcesExpanded ? "chevron.down" : "chevron.right")
                    .font(.system(size: 8, weight: .semibold))
                Text("\(message.sources.count) source\(message.sources.count == 1 ? "" : "s")")
                    .font(.system(size: 10, design: .rounded))
            }
            .foregroundColor(.white.opacity(0.5))
            .padding(.horizontal, 6).padding(.vertical, 3)
        }
        .buttonStyle(.plain)
        .padding(.leading, 8).padding(.top, 4)
    }

    private var sourcesList: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(message.sources.enumerated()), id: \.element.id) { idx, src in
                Button {
                    if let url = URL(string: src.url) { NSWorkspace.shared.open(url) }
                } label: {
                    HStack(alignment: .top, spacing: 6) {
                        Text("[\(idx + 1)]")
                            .font(.system(size: 10, weight: .semibold, design: .monospaced))
                            .foregroundColor(.white.opacity(0.5))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(src.title)
                                .font(.system(size: 11, design: .rounded).weight(.medium))
                                .foregroundColor(.white.opacity(0.85))
                                .lineLimit(1)
                            HStack(spacing: 3) {
                                Image(systemName: "link")
                                    .font(.system(size: 8))
                                    .foregroundColor(.white.opacity(0.4))
                                Text(src.host)
                                    .font(.system(size: 9, design: .rounded))
                                    .foregroundColor(.white.opacity(0.45))
                            }
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 8).padding(.vertical, 5)
                    .background(
                        RoundedRectangle(cornerRadius: 6).fill(Color.white.opacity(0.05))
                    )
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.leading, 8)
        .padding(.top, 2)
        .frame(maxWidth: 360, alignment: .leading)
    }

    private func animateCursor() {
        Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { t in
            if !isStreaming { t.invalidate(); return }
            withAnimation(.linear(duration: 0.1)) { cursorVisible.toggle() }
        }
    }

    private var shailAvatar: some View {
        ZStack {
            Circle().fill(ShailTheme.primaryGradient).frame(width: 26, height: 26)
            Image(systemName: "bolt.fill").font(.system(size: 11, weight: .bold)).foregroundColor(.white)
        }
    }

    @ViewBuilder private var bubbleBackground: some View {
        if message.role == .user {
            RoundedRectangle(cornerRadius: 16).fill(ShailTheme.primaryBlue)
        } else {
            RoundedRectangle(cornerRadius: 16)
                .fill(Color.white.opacity(0.11))
                .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.white.opacity(0.14), lineWidth: 1))
        }
    }
}

// MARK: - Task Progress Card

struct TaskProgressCard: View {
    let taskId: String
    @State private var status: String = "queued"
    @State private var summary: String?
    @State private var isDone = false
    @State private var pollingTimer: Timer?

    var body: some View {
        if !isDone {
            HStack(spacing: 10) {
                statusIcon.frame(width: 20)
                VStack(alignment: .leading, spacing: 2) {
                    Text(statusLabel).font(ShailTheme.captionFont).foregroundColor(.white.opacity(0.85))
                    if let s = summary {
                        Text(s).font(.system(size: 11, design: .rounded))
                            .foregroundColor(.white.opacity(0.5)).lineLimit(2)
                    }
                }
                Spacer()
                Text(taskId.prefix(8)).font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.white.opacity(0.2))
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.white.opacity(0.07))
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(statusBorderColor, lineWidth: 1))
            )
            .onAppear { startPolling() }
            .onDisappear { pollingTimer?.invalidate() }
        }
    }

    private var statusLabel: String {
        switch status {
        case "queued":               return "Task queued…"
        case "planning":             return "Planning…"
        case "executing", "running": return "Executing…"
        case "completed":            return "Done"
        case "failed":               return "Failed"
        default:                     return status.capitalized + "…"
        }
    }

    @ViewBuilder private var statusIcon: some View {
        switch status {
        case "completed":
            Image(systemName: "checkmark.circle.fill").foregroundColor(.green).font(.system(size: 14))
        case "failed":
            Image(systemName: "xmark.circle.fill").foregroundColor(.red).font(.system(size: 14))
        default:
            ProgressView().scaleEffect(0.6).tint(ShailTheme.primaryBlue)
        }
    }

    private var statusBorderColor: Color {
        switch status {
        case "completed": return Color.green.opacity(0.35)
        case "failed":    return Color.red.opacity(0.35)
        default:          return Color.white.opacity(0.12)
        }
    }

    private func startPolling() {
        poll()
        pollingTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { _ in poll() }
    }

    private func poll() {
        Task {
            guard let result = try? await TaskService.shared.fetchStatus(taskId: taskId) else { return }
            await MainActor.run {
                withAnimation(.easeInOut(duration: 0.2)) {
                    status  = result.status
                    summary = result.summary ?? result.result?.summary
                }
                if ["completed", "failed"].contains(result.status) {
                    pollingTimer?.invalidate()
                    DispatchQueue.main.asyncAfter(deadline: .now() + 4) {
                        withAnimation { isDone = true }
                    }
                }
            }
        }
    }
}

// MARK: - Route taken card

struct RouteTakenCard: View {
    let steps: [PlanStep]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                Image(systemName: "arrow.triangle.branch")
                    .font(.system(size: 8, weight: .bold))
                Text("ROUTE TAKEN · \(steps.count) TOOL\(steps.count == 1 ? "" : "S")")
                    .font(.system(size: 8, weight: .bold, design: .monospaced))
            }
            .foregroundColor(.white.opacity(0.35))

            ForEach(steps, id: \.stepId) { step in
                HStack(alignment: .top, spacing: 7) {
                    Circle()
                        .fill(step.success == true ? Color.green : step.executed ? ShailTheme.primaryBlue : Color.white.opacity(0.25))
                        .frame(width: 5, height: 5)
                        .padding(.top, 4)
                    Text(step.description)
                        .font(.system(size: 11, design: .rounded))
                        .foregroundColor(.white.opacity(0.55))
                        .lineLimit(1)
                }
            }
        }
        .padding(.horizontal, 11).padding(.vertical, 9)
        .background(Color.white.opacity(0.04))
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(Color.white.opacity(0.08), lineWidth: 1))
        .cornerRadius(9)
    }
}

// MARK: - Thinking indicator

struct ThinkingBubble: View {
    @State private var scales: [CGFloat] = [0.5, 0.5, 0.5]
    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            ZStack {
                Circle().fill(ShailTheme.primaryGradient).frame(width: 26, height: 26)
                Image(systemName: "bolt.fill").font(.system(size: 11, weight: .bold)).foregroundColor(.white)
            }
            HStack(spacing: 5) {
                ForEach(0..<3, id: \.self) { i in
                    Circle().fill(Color.white.opacity(0.55)).frame(width: 7, height: 7).scaleEffect(scales[i])
                }
            }
            .padding(.horizontal, 14).padding(.vertical, 12)
            .background(RoundedRectangle(cornerRadius: 16).fill(Color.white.opacity(0.10)))
            Spacer(minLength: 48)
        }
        .onAppear {
            for i in 0..<3 {
                withAnimation(.easeInOut(duration: 0.45).repeatForever(autoreverses: true).delay(Double(i) * 0.15)) {
                    scales[i] = 1.0
                }
            }
        }
    }
}
