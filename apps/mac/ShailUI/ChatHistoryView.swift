import SwiftUI
import AppKit

struct ChatHistoryView: View {
    @EnvironmentObject var coordinator: ViewCoordinator
    @ObservedObject private var store = ChatStore.shared
    @Environment(\.dismiss) var dismiss

    @State private var renamingId:  String? = nil
    @State private var renameText:  String  = ""
    @State private var deletingId:  String? = nil
    @State private var searchQuery: String  = ""

    private var filtered: [ChatSession] {
        guard !searchQuery.isEmpty else { return store.sessions }
        let q = searchQuery.lowercased()
        return store.sessions.filter {
            $0.title.lowercased().contains(q) ||
            $0.messages.contains { $0.text.lowercased().contains(q) }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // ── Header ──────────────────────────────────────────────────────
            HStack(spacing: 10) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(ShailTheme.primaryGradient)
                Text("Chat History")
                    .font(ShailTheme.headingFont)
                Spacer()
                Text("\(store.sessions.count) chats")
                    .font(.caption)
                    .foregroundColor(.secondary)
                Button { dismiss() } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 16))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(16)
            .background(Color.white.opacity(0.05))

            Divider().background(Color.white.opacity(0.08))

            // ── Search ───────────────────────────────────────────────────────
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                TextField("Search chats…", text: $searchQuery)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13, design: .rounded))
                if !searchQuery.isEmpty {
                    Button { searchQuery = "" } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                    }.buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(Color.white.opacity(0.05))

            Divider().background(Color.white.opacity(0.06))

            // ── Session list ────────────────────────────────────────────────
            if filtered.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(.system(size: 36))
                        .foregroundColor(.secondary.opacity(0.4))
                    Text(store.sessions.isEmpty
                         ? "No chats yet\nStart a conversation to save history"
                         : "No results for \"\(searchQuery)\"")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 6) {
                        ForEach(filtered) { session in
                            sessionRow(session)
                        }
                    }
                    .padding(12)
                }
            }

            Divider().background(Color.white.opacity(0.06))

            // ── Footer ───────────────────────────────────────────────────────
            HStack {
                Button {
                    coordinator.startNewChat()
                    dismiss()
                } label: {
                    Label("New Chat", systemImage: "square.and.pencil")
                }
                .buttonStyle(GlassButtonStyle(tint: .accentColor))

                Spacer()

                if !store.sessions.isEmpty {
                    Button { exportAll() } label: {
                        Label("Export All", systemImage: "square.and.arrow.up")
                    }
                    .buttonStyle(GlassButtonStyle(tint: .blue))
                }
            }
            .padding(14)
        }
        .frame(width: 500, height: 560)
        .background(ShailTheme.glassBackground(material: .underWindowBackground))
        .overlay(ShailTheme.glassStroke(radius: ShailTheme.cornerRadius))
        .confirmationDialog("Delete this chat?", isPresented: Binding(
            get: { deletingId != nil },
            set: { if !$0 { deletingId = nil } }
        )) {
            Button("Delete", role: .destructive) {
                if let id = deletingId { store.delete(id: id) }
                deletingId = nil
            }
        }
    }

    // MARK: - Session row

    private func sessionRow(_ session: ChatSession) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                ZStack {
                    Circle()
                        .fill(ShailTheme.primaryBlue.opacity(0.15))
                        .frame(width: 32, height: 32)
                    Image(systemName: "bubble.left.fill")
                        .font(.system(size: 13))
                        .foregroundStyle(ShailTheme.primaryGradient)
                }

                VStack(alignment: .leading, spacing: 2) {
                    if renamingId == session.id {
                        TextField("Chat title", text: $renameText)
                            .textFieldStyle(.plain)
                            .font(.system(.subheadline, design: .rounded).weight(.semibold))
                            .foregroundColor(.primary)
                            .onSubmit { commitRename(id: session.id) }
                    } else {
                        Text(session.title)
                            .font(.system(.subheadline, design: .rounded).weight(.semibold))
                            .lineLimit(1)
                            .onTapGesture(count: 2) { startRename(session) }
                    }
                    HStack(spacing: 6) {
                        Text(session.updatedAt.formatted(date: .abbreviated, time: .shortened))
                        Text("·")
                        Text("\(session.messages.count) messages")
                    }
                    .font(.caption2)
                    .foregroundColor(.secondary)
                }

                Spacer()

                if renamingId == session.id {
                    Button { commitRename(id: session.id) } label: {
                        Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
                    }.buttonStyle(.plain)
                    Button { renamingId = nil } label: {
                        Image(systemName: "xmark.circle").foregroundColor(.secondary)
                    }.buttonStyle(.plain)
                } else {
                    Button { startRename(session) } label: {
                        Image(systemName: "pencil").font(.system(size: 11))
                            .foregroundColor(.secondary.opacity(0.7))
                    }.buttonStyle(.plain).help("Rename")

                    Button { exportSession(session) } label: {
                        Image(systemName: "square.and.arrow.up").font(.system(size: 11))
                            .foregroundColor(.secondary.opacity(0.7))
                    }.buttonStyle(.plain).help("Export")

                    Button { deletingId = session.id } label: {
                        Image(systemName: "trash").font(.system(size: 11))
                            .foregroundColor(.red.opacity(0.6))
                    }.buttonStyle(.plain).help("Delete")
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)

            if let last = session.messages.last {
                Text(last.text)
                    .font(.system(size: 11, design: .rounded))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 8)
            }
        }
        .background(
            ZStack {
                VisualEffectBlur(material: .hudWindow, blendingMode: .behindWindow)
                Color.white.opacity(0.04)
            }
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
        .cornerRadius(10)
        .contentShape(Rectangle())
        .onTapGesture {
            guard renamingId == nil else { return }
            coordinator.openSession(session)
            dismiss()
        }
    }

    // MARK: - Rename

    private func startRename(_ session: ChatSession) {
        renamingId = session.id
        renameText = session.title
    }

    private func commitRename(id: String) {
        let title = renameText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !title.isEmpty { store.rename(id: id, title: title) }
        renamingId = nil
    }

    // MARK: - Export

    private func exportSession(_ session: ChatSession) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "\(session.title.replacingOccurrences(of: "/", with: "-")).txt"
        panel.allowedContentTypes = [.plainText]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        try? ChatStore.exportText(session).write(to: url, atomically: true, encoding: .utf8)
    }

    private func exportAll() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "shail_chats_\(String(Date().ISO8601Format().prefix(10))).json"
        panel.allowedContentTypes = [.json]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let parts = store.sessions.compactMap { s -> String? in
            guard let d = ChatStore.exportJSON(s) else { return nil }
            return String(data: d, encoding: .utf8)
        }
        let combined = "[\n" + parts.joined(separator: ",\n") + "\n]"
        try? combined.write(to: url, atomically: true, encoding: .utf8)
    }
}
