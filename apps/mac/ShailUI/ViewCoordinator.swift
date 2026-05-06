import SwiftUI

enum ShailViewMode {
    case popup
    case chat
    case detail
    case birdsEye
}

class ViewCoordinator: ObservableObject {
    @Published var currentView:       ShailViewMode  = .popup
    @Published var messages:          [ChatMessage]  = []
    @Published var lastChatResponse:  String?
    @Published var activeDesktop:     String?
    @Published var selectedNodeId:    String?
    @Published var selectedNodeState: GraphState?
    @Published var activeTaskId:      String?
    @Published var hasError: Bool = false
    @Published var isBirdsEyeOpen: Bool = false
    @Published var showConversationInDashboard: Bool = false

    /// Set by QuickPopupView when user submits a query — ChatOverlayView picks it up on appear.
    @Published var pendingQuery: String? = nil

    /// ID of the currently open chat session (nil = new session not yet saved).
    var currentSessionId: String? = nil

    var collapseToLauncher: (() -> Void)?
    var hidePanel: (() -> Void)?
    var openBirdsEyeWindow: (() -> Void)?
    var resetToPopupSize: (() -> Void)?
    var expandToChatOverlay: (() -> Void)?

    // MARK: - Navigation

    func showPopup() {
        withAnimation { currentView = .popup }
    }

    func showChat() {
        withAnimation { currentView = .chat }
    }

    /// Expand panel to chat size + switch view. Call this instead of showChat() from quick popup.
    func showChatExpanded() {
        expandToChatOverlay?()
        withAnimation { currentView = .chat }
    }

    func showDetail(desktopId: String? = nil, nodeId: String? = nil) {
        if let desktopId { activeDesktop = desktopId }
        if let nodeId    { selectedNodeId = nodeId }
        withAnimation { currentView = .detail }
    }

    func showBirdsEye() {
        openBirdsEyeWindow?()
    }

    func showOfflineDashboard() {
        hasError = true
        showConversationInDashboard = true
        openBirdsEyeWindow?()
    }

    // MARK: - Session helpers

    /// Save current messages as a session (or update existing).
    @discardableResult
    func saveCurrentSession() -> ChatSession? {
        guard !messages.isEmpty else { return nil }
        let title: String
        if let id = currentSessionId,
           let existing = ChatStore.shared.sessions.first(where: { $0.id == id }) {
            title = existing.title   // keep user's custom title if set
        } else {
            title = ChatSession.autoTitle(from: messages)
        }
        var session = ChatSession(
            id: currentSessionId ?? UUID().uuidString,
            title: title,
            messages: messages
        )
        if let id = currentSessionId { session.id = id }
        let saved = ChatStore.shared.upsert(session)
        currentSessionId = saved.id
        return saved
    }

    /// Start a fresh chat (save current first).
    func startNewChat() {
        saveCurrentSession()
        messages = []
        currentSessionId = nil
        pendingQuery = nil
        lastChatResponse = nil
        withAnimation { currentView = .popup }
        resetToPopupSize?()
    }

    /// Open a past session in the chat overlay.
    func openSession(_ session: ChatSession) {
        saveCurrentSession()
        messages = session.messages
        currentSessionId = session.id
        lastChatResponse = session.messages.last(where: { $0.role == .assistant })?.text
        showChatExpanded()
    }
}
