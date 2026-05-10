import SwiftUI
import WebKit
import AppKit

// MARK: - Dashboard tabs

enum BirdsEyeDashboard: String, CaseIterable {
    case langGraph = "Knowledge"
    case memory    = "Memory"

    var icon: String {
        switch self {
        case .langGraph: return "circle.hexagongrid"
        case .memory:    return "brain"
        }
    }
}

// MARK: - Main BirdsEyeView  (3-column: sidebar | content | conversation)

struct BirdsEyeView: View {
    @EnvironmentObject var coordinator: ViewCoordinator
    @EnvironmentObject var backendManager: BackendManager
    @StateObject private var wsClient = BackendWebSocketClient()
    @StateObject private var graphVM  = MemoryDashboardViewModel()
    @State private var selectedNodeId: String?
    @State private var activePanel: BirdsEyeDashboard = .langGraph

    var body: some View {
        HStack(spacing: 0) {
            // Column 1 — Sidebar
            sidebar

            Divider().background(Color.white.opacity(0.08))

            // Column 2 — Graph / Memory dashboard
            contentPanel
                .frame(maxWidth: .infinity)

            // Column 3 — Conversation (only when user explicitly opened from chat overlay)
            if coordinator.showConversationInDashboard && !coordinator.messages.isEmpty {
                Divider().background(Color.white.opacity(0.08))
                conversationPanel
                    .frame(width: 320)
            }
        }
        .frame(minWidth: 1000, minHeight: 700)
        .background(ShailTheme.glassBackground(material: .underWindowBackground))
    }

    // MARK: - Column 1: Sidebar

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            Text("SHAIL")
                .font(ShailTheme.headingFont)
                .foregroundColor(.primary)
                .padding(.bottom, 4)

            HStack(spacing: 6) {
                Circle()
                    .fill(wsClient.isConnected ? Color.green : Color.red)
                    .frame(width: 8, height: 8)
                Text(wsClient.isConnected ? "Connected" : "Disconnected")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Divider()
                .background(Color.white.opacity(0.12))
                .padding(.vertical, 12)

            // Dashboard tabs
            VStack(alignment: .leading, spacing: 2) {
                ForEach(BirdsEyeDashboard.allCases, id: \.self) { panel in
                    dashboardButton(panel)
                }
            }

            // LangGraph live state detail
            if activePanel == .langGraph, let state = wsClient.currentState {
                Divider()
                    .background(Color.white.opacity(0.12))
                    .padding(.vertical, 10)
                langGraphDetail(state)
            }

            Spacer()

            if !backendManager.isAvailable {
                Label("Demo mode — no backend", systemImage: "exclamationmark.triangle.fill")
                    .font(.caption2)
                    .foregroundColor(.orange)
                    .padding(.bottom, 4)
                Button("Fix API Key →") { coordinator.showPopup() }
                    .font(.caption)
                    .foregroundColor(.orange)
                    .buttonStyle(.plain)
                    .padding(.bottom, 8)
            }

            UserProfileChip()
                .padding(.bottom, 8)

            Button(action: { coordinator.showPopup() }) {
                HStack {
                    Image(systemName: "xmark.circle")
                    Text("Close")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
        .padding()
        .frame(width: 240)
        .background(
            ZStack {
                VisualEffectBlur(material: .sidebar, blendingMode: .behindWindow)
                Color.white.opacity(0.04)
            }
        )
    }

    private func dashboardButton(_ panel: BirdsEyeDashboard) -> some View {
        Button(action: { withAnimation(.easeInOut(duration: 0.2)) { activePanel = panel } }) {
            HStack(spacing: 10) {
                Image(systemName: panel.icon).frame(width: 16)
                Text(panel.rawValue)
                    .fontWeight(activePanel == panel ? .semibold : .regular)
                Spacer()
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(activePanel == panel ? Color.accentColor.opacity(0.20) : Color.clear)
            .cornerRadius(8)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundColor(activePanel == panel ? .accentColor : .primary)
    }

    @ViewBuilder
    private func langGraphDetail(_ state: GraphState) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Status: \(state.status)").font(.caption).fontWeight(.bold)
            Text("Node: \(state.currentNode)").font(.caption2)
            Text("Step: \(state.currentStepIndex + 1)/\(state.stepCount)").font(.caption2)
            if let error = state.error {
                Text("Error: \(error)").font(.caption2).foregroundColor(.red)
            }
        }

        if let nodeId = selectedNodeId {
            Divider().padding(.vertical, 6)
            Text("Selected").font(.caption2).fontWeight(.semibold).foregroundColor(.secondary)
            Text(nodeId.replacingOccurrences(of: "_", with: " ").capitalized).font(.caption2)
        }

        if !state.planSteps.isEmpty {
            Divider().padding(.vertical, 6)
            Text("Plan Steps").font(.caption).fontWeight(.semibold)
            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(state.planSteps.enumerated()), id: \.element.stepId) { i, step in
                        HStack(spacing: 6) {
                            Circle().fill(stepColor(step)).frame(width: 6, height: 6)
                            Text("\(i + 1). \(step.description)").font(.caption2).lineLimit(1)
                        }
                    }
                }
            }
            .frame(maxHeight: 180)
        }
    }

    // MARK: - Column 2: Content panel

    @ViewBuilder
    private var contentPanel: some View {
        switch activePanel {
        case .langGraph: knowledgeGraphContent
        case .memory:    MemoryDashboardView()
        }
    }

    private var knowledgeGraphContent: some View {
        ZStack {
            Color(red: 0.05, green: 0.05, blue: 0.08)
            if graphVM.isLoadingEntries {
                VStack(spacing: 10) {
                    ProgressView().tint(.white.opacity(0.4))
                    Text("Loading knowledge graph…")
                        .font(.caption).foregroundColor(.white.opacity(0.35))
                }
            } else if graphVM.entries.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "circle.hexagongrid")
                        .font(.system(size: 52)).foregroundColor(.white.opacity(0.15))
                    Text("No memories yet — Watchdog captures as you work")
                        .font(.caption).foregroundColor(.white.opacity(0.3))
                }
            } else {
                MemoryGraphWebView(entries: graphVM.entries)
            }
        }
        .onAppear { graphVM.loadEntries() }
    }

    private var graphContent: some View {
        ZStack {
            ShailTheme.glassBackground(material: .underPageBackground)
            GraphWebView(
                graphState: Binding(get: { wsClient.currentState }, set: { _ in }),
                onNodeClick: { nodeId in
                    selectedNodeId = nodeId
                    coordinator.selectedNodeId = nodeId
                }
            )
            if wsClient.currentState == nil {
                VStack(spacing: 10) {
                    Image(systemName: "brain.head.profile")
                        .font(.system(size: 60))
                        .foregroundColor(.white.opacity(0.4))
                    Text(backendManager.isAvailable && !coordinator.hasError
                         ? "Waiting for LangGraph state…"
                         : "Showing demo workflow")
                        .font(.headline).foregroundColor(.white.opacity(0.6))
                    if !backendManager.isAvailable || coordinator.hasError {
                        Text("Fix your API key in the sidebar to go live")
                            .font(.caption).foregroundColor(.orange)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(
                    ZStack {
                        VisualEffectBlur(material: .hudWindow, blendingMode: .behindWindow)
                        Color.black.opacity(0.35)
                    }
                )
            }
        }
        .onAppear {
            wsClient.connect()
            if !backendManager.isAvailable || coordinator.hasError {
                wsClient.currentState = MockDataProvider.demoGraphState
            }
        }
    }

    // MARK: - Column 3: Conversation panel

    private var conversationPanel: some View {
        VStack(spacing: 0) {
            // Panel header
            HStack {
                Label("Conversation", systemImage: "bubble.left.and.bubble.right")
                    .font(ShailTheme.headingFont)
                    .foregroundColor(.primary)
                Spacer()
                if coordinator.messages.count > 0 {
                    Button {
                        coordinator.messages.removeAll()
                    } label: {
                        Image(systemName: "trash")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("Clear conversation")
                }

                // Dismiss conversation column (go back to chat overlay)
                Button {
                    coordinator.showConversationInDashboard = false
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("Close conversation panel")
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(Color.white.opacity(0.05))

            Divider().background(Color.white.opacity(0.08))

            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(coordinator.messages) { msg in
                            BirdsEyeMessageBubble(message: msg).id(msg.id)
                        }
                        Color.clear.frame(height: 1).id("conv-bottom")
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                }
                .onChange(of: coordinator.messages.count) { _, _ in
                    withAnimation(.easeOut(duration: 0.2)) {
                        proxy.scrollTo("conv-bottom", anchor: .bottom)
                    }
                }
            }

            Divider().background(Color.white.opacity(0.08))

            // Task queue
            if !taskQueue.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Task Queue")
                        .font(.caption).fontWeight(.semibold).foregroundColor(.secondary)
                        .padding(.horizontal, 12)
                        .padding(.top, 8)

                    ForEach(taskQueue, id: \.id) { task in
                        taskRow(task)
                    }
                }
                .padding(.bottom, 8)
            }
        }
        .background(
            ZStack {
                VisualEffectBlur(material: .sidebar, blendingMode: .behindWindow)
                Color.white.opacity(0.03)
            }
        )
    }

    // Placeholder task queue — wired to wsClient task events
    private var taskQueue: [BirdsEyeTask] {
        // Derive from wsClient if state has tasks; otherwise empty
        guard let state = wsClient.currentState, !state.planSteps.isEmpty else { return [] }
        return state.planSteps.prefix(4).map { step in
            BirdsEyeTask(
                id: step.stepId,
                label: step.description,
                status: step.success == true ? "done" : step.executed ? "running" : "pending"
            )
        }
    }

    private func taskRow(_ task: BirdsEyeTask) -> some View {
        HStack(spacing: 8) {
            Circle()
                .fill(task.status == "done" ? Color.green
                      : task.status == "running" ? Color.blue : Color.gray.opacity(0.5))
                .frame(width: 6, height: 6)
            Text(task.label)
                .font(.caption2)
                .foregroundColor(.secondary)
                .lineLimit(1)
            Spacer()
            Text(task.status)
                .font(.system(size: 9, design: .rounded))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 2)
    }

    func stepColor(_ step: PlanStep) -> Color {
        if let success = step.success { return success ? .green : .red }
        return step.executed ? .blue : .gray
    }
}

// MARK: - Supporting types

struct BirdsEyeTask {
    let id: String
    let label: String
    let status: String
}

// MARK: - Conversation bubble (compact for Bird's Eye panel)

struct BirdsEyeMessageBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            if message.role == .user { Spacer(minLength: 24) }
            if message.role == .assistant {
                ZStack {
                    Circle().fill(ShailTheme.primaryGradient).frame(width: 20, height: 20)
                    Image(systemName: "bolt.fill")
                        .font(.system(size: 9, weight: .bold)).foregroundColor(.white)
                }
            }

            Text(message.text)
                .font(.system(size: 12, design: .rounded))
                .foregroundColor(.white)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(
                    message.role == .user
                        ? AnyShapeStyle(ShailTheme.primaryBlue)
                        : AnyShapeStyle(Color.white.opacity(0.10))
                )
                .cornerRadius(12)
                .fixedSize(horizontal: false, vertical: true)

            if message.role == .user {
                EmptyView()
            } else {
                Spacer(minLength: 24)
            }
        }
    }
}

// MARK: - Memory Dashboard (native SwiftUI — no web dependency)

struct MemoryDashboardView: View {
    @StateObject private var vm = MemoryDashboardViewModel()
    @State private var showGraph = false
    @State private var selectedEntry: MemoryEntry? = nil

    var body: some View {
        ZStack {
            ShailTheme.glassBackground(material: .underPageBackground)

            VStack(spacing: 0) {
                // ── Top bar ──────────────────────────────────────────────
                dashboardTopBar

                Divider().background(Color.white.opacity(0.08))

                // ── Stats row ────────────────────────────────────────────
                statsRow.padding(.horizontal, 20).padding(.vertical, 12)

                Divider().background(Color.white.opacity(0.08))

                if showGraph {
                    // Full-width force graph
                    MemoryGraphWebView(entries: vm.entries)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    // ── Main content (split: Watchdog | Entries) ─────────
                    HStack(spacing: 0) {
                        watchdogSection.frame(width: 280)
                        Divider().background(Color.white.opacity(0.08))
                        memoryEntriesSection
                    }
                }
            }
        }
        .onAppear { vm.load() }
        .sheet(item: $selectedEntry) { entry in
            MemoryDetailView(entry: entry,
                             onDelete: { vm.deleteEntry(id: entry.id) },
                             onUpdate: { updated in
                                 if let idx = vm.entries.firstIndex(where: { $0.id == updated.id }) {
                                     vm.entries[idx] = updated
                                 }
                             })
        }
    }

    // MARK: Top bar

    private var dashboardTopBar: some View {
        HStack(spacing: 12) {
            Label("Memory", systemImage: "brain")
                .font(ShailTheme.headingFont)

            Spacer()

            // Search
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                TextField("Search memories…", text: $vm.searchQuery)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .onSubmit { vm.search() }
                if !vm.searchQuery.isEmpty {
                    Button { vm.searchQuery = ""; vm.load() } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                    }.buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(Color.white.opacity(0.08))
            .cornerRadius(8)
            .frame(width: 200)

            // Source filter
            Picker("Source", selection: $vm.sourceFilter) {
                Text("All").tag("")
                Text("macOS").tag("macos_fs")
                Text("Clipboard").tag("clipboard")
                Text("App Switch").tag("app_switch")
                Text("Browser").tag("browser")
            }
            .pickerStyle(.segmented)
            .frame(width: 280)

            // Graph / List toggle
            Button {
                withAnimation(.easeInOut(duration: 0.2)) { showGraph.toggle() }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: showGraph ? "list.bullet" : "circle.hexagongrid")
                        .font(.system(size: 12))
                    Text(showGraph ? "List" : "Graph")
                        .font(.system(size: 12, design: .rounded))
                }
                .foregroundColor(showGraph ? .accentColor : .secondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(showGraph ? Color.accentColor.opacity(0.15) : Color.white.opacity(0.07))
                .cornerRadius(7)
            }
            .buttonStyle(.plain)

            // Export all
            Button { vm.exportAll() } label: {
                Image(systemName: "square.and.arrow.up").font(.system(size: 13))
            }
            .buttonStyle(.plain)
            .foregroundColor(.secondary)
            .help("Export all memories as JSON")

            // Refresh
            Button { vm.load() } label: {
                Image(systemName: "arrow.clockwise").font(.system(size: 13))
            }
            .buttonStyle(.plain)
            .foregroundColor(.secondary)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .background(Color.white.opacity(0.04))
    }

    // MARK: Stats row

    private var statsRow: some View {
        HStack(spacing: 20) {
            statPill(icon: "square.stack.3d.up", label: "Total", value: "\(vm.totalEntries)")
            statPill(icon: "calendar", label: "This Week", value: "\(vm.thisWeek)")
            statPill(icon: "pin.fill", label: "Pinned", value: "\(vm.pinnedCount)")
            statPill(icon: "internaldrive", label: "DB Size", value: vm.dbSizeLabel)

            Spacer()

            // Capacity bar
            VStack(alignment: .trailing, spacing: 4) {
                Text("Storage").font(.caption2).foregroundColor(.secondary)
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.white.opacity(0.1))
                        .frame(width: 120, height: 6)
                    RoundedRectangle(cornerRadius: 3)
                        .fill(vm.capacityPercent > 80 ? Color.red : ShailTheme.primaryBlue)
                        .frame(width: 120 * CGFloat(vm.capacityPercent) / 100, height: 6)
                }
                Text("\(vm.usedHuman) / 500 MB")
                    .font(.system(size: 9, design: .rounded))
                    .foregroundColor(.secondary)
            }
        }
    }

    private func statPill(icon: String, label: String, value: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundColor(.accentColor)
            VStack(alignment: .leading, spacing: 1) {
                Text(value)
                    .font(.system(.body, design: .rounded).weight(.semibold))
                Text(label)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.white.opacity(0.07))
        .cornerRadius(10)
    }

    // MARK: Watchdog section (left column)

    private var watchdogSection: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {

                // Control card
                glassCard {
                    HStack(spacing: 10) {
                        Image(systemName: "brain")
                            .font(.system(size: 24))
                            .foregroundStyle(vm.watchdogRunning ? Color.green : Color.gray)

                        VStack(alignment: .leading, spacing: 2) {
                            Text("Memory Watchdog")
                                .font(ShailTheme.headingFont)
                            HStack(spacing: 5) {
                                Circle()
                                    .fill(vm.watchdogRunning ? Color.green : Color.red)
                                    .frame(width: 6, height: 6)
                                Text(vm.watchdogStatus)
                                    .font(.caption).foregroundColor(.secondary)
                            }
                        }

                        Spacer()
                    }

                    HStack(spacing: 8) {
                        Button("Start") { vm.startWatchdog() }
                            .buttonStyle(GlassButtonStyle(tint: .green))
                            .disabled(vm.watchdogRunning || vm.watchdogBusy)
                        Button("Stop") { vm.stopWatchdog() }
                            .buttonStyle(GlassButtonStyle(tint: .red))
                            .disabled(!vm.watchdogRunning || vm.watchdogBusy)
                    }
                    .padding(.top, 8)

                    if let err = vm.watchdogError {
                        Text(err).font(.caption2).foregroundColor(.red).padding(.top, 4)
                    }
                }

                // Active watchers
                glassCard {
                    Text("Active Watchers")
                        .font(ShailTheme.headingFont).padding(.bottom, 6)

                    ForEach(MemoryDashboardViewModel.watchers, id: \.name) { w in
                        HStack(spacing: 8) {
                            Image(systemName: w.icon)
                                .frame(width: 16)
                                .foregroundColor(vm.watchdogRunning ? .accentColor : .secondary)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(w.name).font(.caption)
                                Text(w.detail).font(.caption2).foregroundColor(.secondary)
                            }
                            Spacer()
                            Circle()
                                .fill(vm.watchdogRunning ? Color.green : Color.gray.opacity(0.3))
                                .frame(width: 5, height: 5)
                        }
                        .padding(.vertical, 4)
                    }
                }

                // Terminal reference card
                glassCard {
                    VStack(alignment: .leading, spacing: 6) {
                        Label("Start Externally", systemImage: "terminal")
                            .font(ShailTheme.headingFont).padding(.bottom, 4)
                        codeSnip("./start_shail.sh",
                                 note: "Starts all services + Watchdog")
                        codeSnip("./native/mac/MemoryWatchdog/.build/release/MemoryWatchdog",
                                 note: "Watchdog binary only")
                    }
                }

                Spacer(minLength: 0)
            }
            .padding(16)
        }
        .background(Color.white.opacity(0.02))
    }

    // MARK: Memory entries section (right column)

    private var memoryEntriesSection: some View {
        VStack(spacing: 0) {
            if vm.isLoadingEntries {
                ProgressView("Loading memories…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.entries.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "tray")
                        .font(.system(size: 40))
                        .foregroundColor(.white.opacity(0.25))
                    Text(vm.searchQuery.isEmpty
                         ? "No memories yet — Watchdog captures as you work"
                         : "No results for \"\(vm.searchQuery)\"")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 10) {
                        ForEach(vm.entries) { entry in
                            MemoryEntryCard(entry: entry,
                                            onSelect: { selectedEntry = entry },
                                            onDelete: { vm.deleteEntry(id: entry.id) })
                        }
                    }
                    .padding(16)
                }
            }
        }
    }

    // MARK: Helpers

    @ViewBuilder
    private func glassCard<C: View>(@ViewBuilder content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            content().padding(14)
        }
        .background(
            ZStack {
                VisualEffectBlur(material: .hudWindow, blendingMode: .behindWindow)
                Color.white.opacity(0.05)
            }
        )
        .overlay(ShailTheme.glassStroke(radius: ShailTheme.innerRadius))
        .cornerRadius(ShailTheme.innerRadius)
    }

    private func codeSnip(_ code: String, note: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(code)
                .font(.system(.caption2, design: .monospaced))
                .foregroundColor(.green.opacity(0.85))
                .padding(.horizontal, 6).padding(.vertical, 3)
                .background(Color.black.opacity(0.35))
                .cornerRadius(5)
            Text(note).font(.caption2).foregroundColor(.secondary)
        }
    }
}

// MARK: - Memory Entry Card

struct MemoryEntryCard: View {
    let entry: MemoryEntry
    var onSelect: (() -> Void)? = nil
    var onDelete: (() -> Void)? = nil
    @State private var isHovered = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Image(systemName: entry.icon)
                    .font(.system(size: 13))
                    .foregroundColor(.accentColor)
                    .frame(width: 20)

                Text(entry.title.isEmpty ? entry.source : entry.title)
                    .font(.system(.caption, design: .rounded).weight(.semibold))
                    .lineLimit(1)

                Spacer()

                Text(entry.tier)
                    .font(.system(size: 9, design: .rounded))
                    .padding(.horizontal, 5).padding(.vertical, 2)
                    .background(tierColor(entry.tier).opacity(0.18))
                    .foregroundColor(tierColor(entry.tier))
                    .cornerRadius(4)

                Text(entry.relativeTime)
                    .font(.system(size: 9, design: .rounded))
                    .foregroundColor(.secondary)

                // Quick delete on hover
                if isHovered, let del = onDelete {
                    Button { del() } label: {
                        Image(systemName: "trash")
                            .font(.system(size: 10))
                            .foregroundColor(.red.opacity(0.7))
                    }
                    .buttonStyle(.plain)
                    .transition(.opacity)
                }
            }

            Text(entry.snippet)
                .font(.system(size: 11, design: .rounded))
                .foregroundColor(.white.opacity(0.65))
                .lineLimit(2)

            // Source label
            HStack(spacing: 4) {
                Image(systemName: sourceIcon(entry.source)).font(.system(size: 9))
                Text(sourceLabel(entry.source)).font(.system(size: 9, design: .rounded))
            }
            .foregroundColor(.secondary)
        }
        .padding(12)
        .background(
            ZStack {
                VisualEffectBlur(material: .hudWindow, blendingMode: .behindWindow)
                Color.white.opacity(isHovered ? 0.09 : 0.05)
            }
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(isHovered ? Color.accentColor.opacity(0.35) : Color.white.opacity(0.10),
                        lineWidth: 1)
        )
        .cornerRadius(10)
        .onHover { isHovered = $0 }
        .onTapGesture { onSelect?() }
        .animation(.easeInOut(duration: 0.15), value: isHovered)
    }

    private func tierColor(_ tier: String) -> Color {
        switch tier {
        case "important":   return .yellow
        case "ephemeral":   return .blue
        case "path_index":  return .green
        default:            return .gray
        }
    }

    private func sourceIcon(_ src: String) -> String {
        switch src {
        case "clipboard":  return "doc.on.clipboard"
        case "macos_fs":   return "folder"
        case "app_switch": return "apps.iphone"
        case "browser":    return "globe"
        case "manual":     return "pin"
        default:           return "memorychip"
        }
    }

    private func sourceLabel(_ src: String) -> String {
        switch src {
        case "clipboard":  return "Clipboard"
        case "macos_fs":   return "macOS File"
        case "app_switch": return "App Monitor"
        case "browser":    return "Browser"
        case "manual":     return "Manual"
        default:           return src.isEmpty ? "Unknown" : src
        }
    }
}

// MARK: - Memory Detail Sheet

struct MemoryDetailView: View {
    var entry: MemoryEntry
    var onDelete: () -> Void
    var onUpdate: (MemoryEntry) -> Void
    @Environment(\.dismiss) var dismiss
    @State private var isDeleting = false
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // ── Header ──────────────────────────────────────────────────────
            HStack(spacing: 10) {
                Image(systemName: entry.icon)
                    .font(.system(size: 16))
                    .foregroundColor(.accentColor)
                VStack(alignment: .leading, spacing: 2) {
                    Text(entry.title.isEmpty ? sourceLabel(entry.source) : entry.title)
                        .font(ShailTheme.headingFont)
                        .lineLimit(2)
                    HStack(spacing: 10) {
                        Label(sourceLabel(entry.source), systemImage: entry.icon)
                        Text("·").foregroundColor(.secondary)
                        Label(entry.tier, systemImage: "tag")
                            .foregroundColor(tierColor(entry.tier))
                        Text("·").foregroundColor(.secondary)
                        Label(entry.relativeTime, systemImage: "clock")
                    }
                    .font(.caption)
                    .foregroundColor(.secondary)
                }
                Spacer()
                Button { dismiss() } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 18))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(16)
            .background(Color.white.opacity(0.05))

            Divider().background(Color.white.opacity(0.08))

            // ── Full content ────────────────────────────────────────────────
            ScrollView {
                Text(entry.fullContent ?? entry.snippet)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(.primary.opacity(0.9))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
            }

            Divider().background(Color.white.opacity(0.08))

            // ── Actions ─────────────────────────────────────────────────────
            HStack(spacing: 10) {
                Button {
                    exportEntry()
                } label: {
                    Label("Export", systemImage: "square.and.arrow.up")
                }
                .buttonStyle(GlassButtonStyle(tint: .accentColor))

                Button {
                    let txt = entry.fullContent ?? entry.snippet
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(txt, forType: .string)
                    copied = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { copied = false }
                } label: {
                    Label(copied ? "Copied!" : "Copy", systemImage: copied ? "checkmark" : "doc.on.clipboard")
                }
                .buttonStyle(GlassButtonStyle(tint: .blue))

                Spacer()

                Button {
                    isDeleting = true
                } label: {
                    Label("Delete", systemImage: "trash")
                }
                .buttonStyle(GlassButtonStyle(tint: .red))
                .confirmationDialog("Delete this memory permanently?", isPresented: $isDeleting) {
                    Button("Delete", role: .destructive) {
                        onDelete()
                        dismiss()
                    }
                }
            }
            .padding(16)
        }
        .frame(width: 640, height: 520)
        .background(ShailTheme.glassBackground(material: .underWindowBackground))
        .overlay(ShailTheme.glassStroke(radius: ShailTheme.cornerRadius))
    }

    private func tierColor(_ tier: String) -> Color {
        switch tier {
        case "important": return .yellow
        case "ephemeral":  return .blue
        default:           return .gray
        }
    }

    private func sourceLabel(_ src: String) -> String {
        switch src {
        case "clipboard":  return "Clipboard"
        case "macos_fs":   return "macOS File"
        case "app_switch": return "App Monitor"
        case "browser":    return "Browser"
        case "manual":     return "Manual"
        default:           return src.isEmpty ? "Unknown" : src
        }
    }

    private func exportEntry() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "\(entry.title.isEmpty ? entry.id : entry.title).txt"
            .replacingOccurrences(of: "/", with: "-")
        panel.allowedContentTypes = [.plainText]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let body = """
Title:     \(entry.title)
Source:    \(entry.source)
Tier:      \(entry.tier)
Timestamp: \(entry.timestamp)

---

\(entry.fullContent ?? entry.snippet)
"""
        try? body.write(to: url, atomically: true, encoding: .utf8)
    }
}

// MARK: - Memory Entry model

struct MemoryEntry: Identifiable {
    let id: String
    let tier: String
    let title: String
    let snippet: String
    let source: String
    let timestamp: String
    var fullContent: String? = nil   // full text, loaded on detail open

    var relativeTime: String {
        guard let date = ISO8601DateFormatter().date(from: timestamp) else { return "" }
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .abbreviated
        return f.localizedString(for: date, relativeTo: Date())
    }

    var icon: String {
        switch source {
        case "clipboard":   return "doc.on.clipboard"
        case "app_switch":  return "apps.iphone"
        case "macos_fs":    return "folder"
        case "browser":     return "globe"
        case "manual":      return "pin"
        default:            return "memorychip"
        }
    }
}

// MARK: - Memory Dashboard ViewModel

final class MemoryDashboardViewModel: ObservableObject {
    // Watchdog state
    @Published var watchdogRunning = false
    @Published var watchdogBusy   = false
    @Published var watchdogStatus = "Checking…"
    @Published var watchdogError: String?

    // Stats
    @Published var totalEntries   = 0
    @Published var thisWeek       = 0
    @Published var pinnedCount    = 0
    @Published var dbSizeLabel    = "—"
    @Published var capacityPercent: Double = 0
    @Published var usedHuman      = "—"

    // Entries
    @Published var entries: [MemoryEntry] = []
    @Published var isLoadingEntries = false
    @Published var searchQuery = ""
    @Published var sourceFilter = ""

    private var repoRoot: String { ServiceLauncher.shared.repoRoot }
    private var pidFile:  String { repoRoot + "/run/memory_watchdog.pid" }
    private var binary:   String { repoRoot + "/native/mac/MemoryWatchdog/.build/release/MemoryWatchdog" }
    private var dbPath:   String {
        // Prefer the Chroma persistent store; fallback to sqlite
        let chroma = NSHomeDirectory() + "/Library/Application Support/SHAIL/memory/chroma/chroma.sqlite3"
        if FileManager.default.fileExists(atPath: chroma) { return chroma }
        return repoRoot + "/shail_memory.sqlite3"
    }
    private let apiBase = URL(string: "http://localhost:8000")!

    struct WatcherInfo { let name: String; let icon: String; let detail: String }
    static let watchers: [WatcherInfo] = [
        WatcherInfo(name: "File System", icon: "folder", detail: "~/Documents, ~/Desktop, ~/Downloads"),
        WatcherInfo(name: "Clipboard",   icon: "doc.on.clipboard", detail: "Text > 100 chars, polls every 2s"),
        WatcherInfo(name: "App Monitor", icon: "apps.iphone", detail: "Tracks app switches via NSWorkspace"),
    ]

    func load() {
        checkWatchdogStatus()
        loadStats()
        loadEntries()
    }

    func search() {
        loadEntries()
    }

    // MARK: - Watchdog Control

    func checkWatchdogStatus() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            let running = self.isWatchdogRunning()
            DispatchQueue.main.async {
                self.watchdogRunning = running
                self.watchdogStatus  = running ? "Running" : "Stopped"
            }
        }
    }

    func startWatchdog() {
        guard !watchdogBusy else { return }
        watchdogBusy = true
        watchdogError = nil
        watchdogStatus = "Starting…"

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            guard FileManager.default.isExecutableFile(atPath: self.binary) else {
                DispatchQueue.main.async {
                    self.watchdogBusy   = false
                    self.watchdogStatus = "Binary not built"
                    self.watchdogError  = "Run: cd native/mac/MemoryWatchdog && swift build -c release"
                }
                return
            }

            let task = Process()
            task.launchPath = self.binary
            task.currentDirectoryPath = self.repoRoot

            let logPath = self.repoRoot + "/logs/memory_watchdog.log"
            FileManager.default.createFile(atPath: logPath, contents: nil)
            if let h = FileHandle(forWritingAtPath: logPath) {
                task.standardOutput = h
                task.standardError  = h
            }

            do {
                try task.run()
                let pid = String(task.processIdentifier)
                try? pid.write(toFile: self.pidFile, atomically: true, encoding: .utf8)
                DispatchQueue.main.async {
                    self.watchdogBusy    = false
                    self.watchdogRunning = true
                    self.watchdogStatus  = "Running"
                }
            } catch {
                DispatchQueue.main.async {
                    self.watchdogBusy   = false
                    self.watchdogStatus = "Failed to start"
                    self.watchdogError  = error.localizedDescription
                }
            }
        }
    }

    func stopWatchdog() {
        guard !watchdogBusy else { return }
        watchdogBusy = true
        watchdogStatus = "Stopping…"

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }

            if let pidStr = try? String(contentsOfFile: self.pidFile, encoding: .utf8),
               let pid = Int32(pidStr.trimmingCharacters(in: .whitespacesAndNewlines)) {
                kill(pid, SIGTERM)
                try? FileManager.default.removeItem(atPath: self.pidFile)
            } else {
                let task = Process()
                task.launchPath = "/usr/bin/pkill"
                task.arguments  = ["-x", "MemoryWatchdog"]
                try? task.run()
                task.waitUntilExit()
            }

            DispatchQueue.main.async {
                self.watchdogBusy    = false
                self.watchdogRunning = false
                self.watchdogStatus  = "Stopped"
            }
        }
    }

    // MARK: - Stats

    private func loadStats() {
        // DB file size
        if let attrs = try? FileManager.default.attributesOfItem(atPath: dbPath),
           let sz = attrs[.size] as? Int {
            dbSizeLabel = ByteCountFormatter.string(fromByteCount: Int64(sz), countStyle: .file)
        }

        // Capacity from API — use authenticated endpoint so count is accurate
        Task {
            let apiKey = SettingsManager.shared.settings.apiKey
            guard let url = URL(string: "http://localhost:8000/api/v2/memories?limit=1") else { return }
            var req = URLRequest(url: url)
            req.timeoutInterval = 6
            if !apiKey.isEmpty { req.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization") }
            if let (data, _) = try? await URLSession.shared.data(for: req),
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let total = json["total"] as? Int {
                await MainActor.run { self.totalEntries = total }
            }
        }

        // Path index stats
        Task {
            if let url = URL(string: "/path-index/stats", relativeTo: apiBase),
               let (data, _) = try? await URLSession.shared.data(from: url),
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                // stats returns {total, by_type, ...}
                _ = json  // we already have total from search; future: show by_type
            }
        }
    }

    // MARK: - Entries

    func loadEntries() {
        isLoadingEntries = true
        Task {
            // Primary: /api/v2/memories with Bearer auth — queries ALL namespaces (user + browser + local)
            let loaded = await fetchAllEntries()
            await MainActor.run {
                self.entries          = loaded
                self.isLoadingEntries = false
                if !loaded.isEmpty    { self.totalEntries = loaded.count }
            }
        }
    }

    /// Single unified fetch — uses /api/v2/memories (auth) then falls back to /memory/search (anon).
    private func fetchAllEntries() async -> [MemoryEntry] {
        let apiKey = SettingsManager.shared.settings.apiKey
        let q      = searchQuery.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""

        // Fetch ALL entries — apply source filter client-side after canonicalisation
        var comps = URLComponents(string: "http://localhost:8000/api/v2/memories")!
        comps.queryItems = [
            URLQueryItem(name: "limit", value: "100"),
            URLQueryItem(name: "q",     value: q),
        ]
        guard let url = comps.url else { return [] }

        var req = URLRequest(url: url)
        req.timeoutInterval = 12
        if !apiKey.isEmpty {
            req.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        }

        if let (data, resp) = try? await URLSession.shared.data(for: req),
           let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let items = json["items"] as? [[String: Any]], !items.isEmpty {

            return items.compactMap { item in
                guard let id = item["id"] as? String else { return nil }
                let rawSource  = item["sourceApp"] as? String ?? item["source"] as? String ?? ""
                let eventType  = item["eventType"] as? String ?? ""
                let canonical  = canonicalSource(rawSource: rawSource, eventType: eventType)
                // Client-side source filter (after canonical normalisation)
                if !sourceFilter.isEmpty && canonical != sourceFilter { return nil }
                let tier = item["tier"] as? String ?? "important"
                return MemoryEntry(
                    id: id, tier: tier,
                    title:   item["title"]   as? String ?? "",
                    snippet: String((item["summary"] as? String ?? item["content"] as? String ?? "").prefix(220)),
                    source:  canonical,
                    timestamp: item["timestamp"] as? String ?? ""
                )
            }
        }

        // Fallback: unauthenticated /memory/search (macOS watchdog records in local namespace)
        return await fetchUnauthenticated(q: q)
    }

    private func fetchUnauthenticated(q: String) async -> [MemoryEntry] {
        let qEnc = q.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        var path = "/memory/search?q=\(qEnc)&k=40"
        if !sourceFilter.isEmpty { path += "&tiers=ephemeral,important" }

        guard let url = URL(string: path, relativeTo: apiBase),
              let (data, resp) = try? await URLSession.shared.data(from: url),
              let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = json["items"] as? [[String: Any]]
        else { return [] }

        return items.compactMap { item in
            let id        = item["id"] as? String ?? UUID().uuidString
            let rawSource = item["source"] as? String ?? ""
            if !sourceFilter.isEmpty && rawSource != sourceFilter { return nil }
            return MemoryEntry(
                id: id,
                tier:      item["tier"]      as? String ?? "ephemeral",
                title:     item["title"]     as? String ?? "",
                snippet:   String((item["content"] as? String ?? "").prefix(220)),
                source:    canonicalSource(rawSource: rawSource, eventType: ""),
                timestamp: item["timestamp"] as? String ?? ""
            )
        }
    }

    /// Normalise raw `sourceApp` / `source` values into the canonical keys used by MemoryEntry.icon.
    private func canonicalSource(rawSource: String, eventType: String) -> String {
        switch rawSource {
        case "clipboard":                    return "clipboard"
        case "macos_fs", "local_file":       return "macos_fs"
        case "app_switch":                   return "app_switch"
        case "macos_screen", "screen":       return "macos_fs"
        case "manual", "pin":               return "manual"
        case "browser":                      return "browser"
        default:
            // Infer browser from event type
            if eventType == "page_visit" || eventType == "ai_conversation"
                || rawSource.lowercased().contains("browser")
                || rawSource.lowercased().contains("chrome")
                || rawSource.lowercased().contains("safari")
                || rawSource.lowercased().contains("firefox") {
                return "browser"
            }
            return rawSource.isEmpty ? "browser" : rawSource
        }
    }

    // MARK: - Delete

    func deleteEntry(id: String) {
        let apiKey = SettingsManager.shared.settings.apiKey
        // Remove locally immediately
        entries.removeAll { $0.id == id }
        totalEntries = entries.count
        // Fire-and-forget HTTP DELETE
        guard let url = URL(string: "http://localhost:8000/api/v2/memories/\(id)") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        if !apiKey.isEmpty { req.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization") }
        URLSession.shared.dataTask(with: req).resume()
    }

    // MARK: - Export all

    func exportAll() {
        guard !entries.isEmpty else { return }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "shail_memories_\(ISO8601DateFormatter().string(from: Date()).prefix(10)).json"
        panel.allowedContentTypes = [.json]
        guard panel.runModal() == .OK, let url = panel.url else { return }

        let payload: [[String: String]] = entries.map { e in
            ["id": e.id, "title": e.title, "source": e.source, "tier": e.tier,
             "timestamp": e.timestamp, "snippet": e.snippet]
        }
        guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted]) else { return }
        try? data.write(to: url)
    }

    // MARK: - Private helpers

    private func isWatchdogRunning() -> Bool {
        if let pidStr = try? String(contentsOfFile: pidFile, encoding: .utf8),
           let pid = Int32(pidStr.trimmingCharacters(in: .whitespacesAndNewlines)),
           kill(pid, 0) == 0 { return true }
        let task = Process()
        task.launchPath = "/usr/bin/pgrep"
        task.arguments  = ["-x", "MemoryWatchdog"]
        let pipe = Pipe()
        task.standardOutput = pipe
        guard (try? task.run()) != nil else { return false }
        task.waitUntilExit()
        return task.terminationStatus == 0
    }
}

// MARK: - Glass button style

struct GlassButtonStyle: ButtonStyle {
    var tint: Color
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.caption, design: .rounded).weight(.semibold))
            .foregroundColor(tint)
            .padding(.horizontal, 14).padding(.vertical, 7)
            .background(
                ZStack {
                    VisualEffectBlur(material: .hudWindow, blendingMode: .behindWindow)
                    tint.opacity(configuration.isPressed ? 0.25 : 0.12)
                }
            )
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(tint.opacity(0.4), lineWidth: 1))
            .cornerRadius(8)
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
    }
}

// MARK: - Memory Force Graph (D3.js via WKWebView)

struct MemoryGraphWebView: NSViewRepresentable {
    let entries: [MemoryEntry]

    func makeCoordinator() -> Coordinator { Coordinator() }

    class Coordinator {
        var lastEntryCount = -1
    }

    func makeNSView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        let wv  = WKWebView(frame: .zero, configuration: cfg)
        wv.setValue(false, forKey: "drawsBackground")
        loadGraph(into: wv)
        return wv
    }

    func updateNSView(_ wv: WKWebView, context: Context) {
        guard entries.count != context.coordinator.lastEntryCount else { return }
        context.coordinator.lastEntryCount = entries.count
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.8) {
            let js = self.buildUpdateJS()
            wv.evaluateJavaScript(js, completionHandler: nil)
        }
    }

    // MARK: - Build initial HTML

    private func loadGraph(into wv: WKWebView) {
        let html = """
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="UTF-8">
        <style>
          * { box-sizing: border-box; margin: 0; padding: 0; }
          body { background: transparent; overflow: hidden; font-family: -apple-system, sans-serif; }
          #graph { width: 100vw; height: 100vh; }
          .tooltip {
            position: absolute; background: rgba(0,0,0,0.75);
            color: #fff; padding: 6px 10px; border-radius: 8px;
            font-size: 11px; pointer-events: none; max-width: 200px;
            opacity: 0; transition: opacity 0.15s;
          }
          .legend { position: absolute; bottom: 16px; left: 16px; display: flex; gap: 12px; }
          .legend-item { display: flex; align-items: center; gap: 5px;
            color: rgba(255,255,255,0.65); font-size: 11px; }
          .legend-dot { width: 8px; height: 8px; border-radius: 50%; }
        </style>
        </head>
        <body>
        <svg id="graph"></svg>
        <div class="tooltip" id="tooltip"></div>
        <div class="legend" id="legend"></div>
        <script src="https://d3js.org/d3.v7.min.js" onerror="fallback()"></script>
        <script>
        var nodes = [], links = [];

        var sourceColors = {
          "macos_fs":  "#4CAF50",
          "clipboard": "#2196F3",
          "app_switch":"#9C27B0",
          "browser":   "#FF9800",
          "manual":    "#F44336",
          "default":   "#607D8B"
        };

        function colorFor(source) {
          return sourceColors[source] || sourceColors.default;
        }

        function fallback() {
          d3 = null;
          document.getElementById("graph").innerHTML =
            '<text x="50%" y="50%" text-anchor="middle" fill="rgba(255,255,255,0.4)" font-size="14" font-family="-apple-system,sans-serif" dy=".3em">Graph requires internet (D3.js CDN)</text>';
        }

        function buildLegend() {
          var sources = [...new Set(nodes.map(n => n.source))];
          var legend = document.getElementById("legend");
          legend.innerHTML = sources.map(s =>
            '<div class="legend-item"><div class="legend-dot" style="background:' + colorFor(s) + '"></div>' + s + '</div>'
          ).join("");
        }

        function renderGraph() {
          if (typeof d3 === "undefined") { fallback(); return; }
          var svg = d3.select("#graph");
          svg.selectAll("*").remove();
          var w = window.innerWidth, h = window.innerHeight;
          svg.attr("width", w).attr("height", h);

          var sim = d3.forceSimulation(nodes)
            .alphaDecay(0.06)
            .force("link", d3.forceLink(links).id(d => d.id).distance(80).strength(0.4))
            .force("charge", d3.forceManyBody().strength(-180))
            .force("center", d3.forceCenter(w/2, h/2))
            .force("collision", d3.forceCollide().radius(22));

          var link = svg.append("g").selectAll("line")
            .data(links).join("line")
            .attr("stroke", "#00D4FF")
            .attr("stroke-opacity", 0.45)
            .attr("stroke-width", 1.5);

          var node = svg.append("g").selectAll("g")
            .data(nodes).join("g")
            .call(d3.drag()
              .on("start", (e,d) => { d.fx=d.x; d.fy=d.y; })
              .on("drag",  (e,d) => { d.fx=e.x; d.fy=e.y; })
              .on("end",   () => { /* keep node pinned — no sim restart */ })
            );

          node.append("circle")
            .attr("r", d => 10 + Math.min(d.importance * 12, 10))
            .attr("fill", "#FFFFFF")
            .attr("fill-opacity", 0.92)
            .attr("stroke", "#00D4FF")
            .attr("stroke-width", 1.5);

          node.append("text")
            .text(d => (d.title || d.source).substring(0, 14))
            .attr("text-anchor", "middle")
            .attr("dy", "0.35em")
            .attr("fill", "rgba(255,255,255,0.9)")
            .attr("font-size", "9px")
            .attr("font-family", "-apple-system, sans-serif")
            .attr("pointer-events", "none");

          // Tooltip
          var tip = document.getElementById("tooltip");
          node.on("mouseover", (e, d) => {
            tip.style.opacity = "1";
            tip.style.left = (e.pageX + 12) + "px";
            tip.style.top  = (e.pageY - 28) + "px";
            tip.textContent = (d.title || d.source) + (d.snippet ? "\\n" + d.snippet.substring(0,80) : "");
          }).on("mousemove", e => {
            tip.style.left = (e.pageX + 12) + "px";
            tip.style.top  = (e.pageY - 28) + "px";
          }).on("mouseout", () => { tip.style.opacity = "0"; });

          sim.on("tick", () => {
            link.attr("x1", d=>d.source.x).attr("y1", d=>d.source.y)
                .attr("x2", d=>d.target.x).attr("y2", d=>d.target.y);
            node.attr("transform", d => "translate(" + Math.max(12,Math.min(w-12,d.x)) + "," + Math.max(12,Math.min(h-12,d.y)) + ")");
          });

          buildLegend();
        }

        function updateGraph(nodesJSON, linksJSON) {
          nodes = JSON.parse(nodesJSON);
          links = JSON.parse(linksJSON);
          renderGraph();
        }
        </script>
        </body>
        </html>
        """
        wv.loadHTMLString(html, baseURL: nil)
        // Inject data after load
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            let js = self.buildUpdateJS()
            wv.evaluateJavaScript(js, completionHandler: nil)
        }
    }

    private func buildUpdateJS() -> String {
        let nodes = entries.enumerated().map { i, e in
            [
                "id": e.id,
                "title": String(e.title.prefix(30)),
                "source": e.source,
                "snippet": String(e.snippet.prefix(80)),
                "importance": 0.5
            ] as [String: Any]
        }

        // Edges: connect entries with same source (chain)
        var links: [[String: Any]] = []
        var bySource: [String: [String]] = [:]
        for e in entries { bySource[e.source, default: []].append(e.id) }
        for (_, ids) in bySource {
            for i in 0..<min(ids.count - 1, 6) {
                links.append(["source": ids[i], "target": ids[i+1]])
            }
        }

        guard let nodesData = try? JSONSerialization.data(withJSONObject: nodes),
              let linksData = try? JSONSerialization.data(withJSONObject: links),
              let nodesStr  = String(data: nodesData, encoding: .utf8),
              let linksStr  = String(data: linksData, encoding: .utf8) else {
            return ""
        }
        return "if(typeof updateGraph==='function'){updateGraph(\(jsString(nodesStr)), \(jsString(linksStr)));}"
    }

    private func jsString(_ s: String) -> String {
        let escaped = s.replacingOccurrences(of: "'", with: "\\'")
        return "'\(escaped)'"
    }
}
