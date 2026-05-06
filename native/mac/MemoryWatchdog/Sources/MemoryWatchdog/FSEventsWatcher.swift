import Foundation
import CoreServices

/// Watches ~/Documents, ~/Desktop, ~/Downloads via FSEvents.
/// On file create/modify: extracts content, scores importance, sends to SHAIL memory.
final class FSEventsWatcher {

    private var stream: FSEventStreamRef?

    private let watchPaths: [String] = [
        NSHomeDirectory() + "/Documents",
        NSHomeDirectory() + "/Desktop",
        NSHomeDirectory() + "/Downloads",
    ]

    // MARK: - Start / Stop

    func start() {
        let cfPaths = watchPaths as CFArray
        var ctx = FSEventStreamContext(
            version: 0,
            info: Unmanaged.passRetained(self).toOpaque(),
            retain: nil,
            release: nil,
            copyDescription: nil
        )
        stream = FSEventStreamCreate(
            nil,
            fsEventsCallback,
            &ctx,
            cfPaths,
            FSEventStreamEventId(kFSEventStreamEventIdSinceNow),
            2.0,   // latency seconds
            FSEventStreamCreateFlags(
                kFSEventStreamCreateFlagUseCFTypes |
                kFSEventStreamCreateFlagFileEvents
            )
        )
        guard let stream else { return }
        FSEventStreamScheduleWithRunLoop(stream, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
        FSEventStreamStart(stream)
        print("[FSEventsWatcher] Watching: \(watchPaths.joined(separator: ", "))")
    }

    func stop() {
        guard let stream else { return }
        FSEventStreamStop(stream)
        FSEventStreamInvalidate(stream)
        FSEventStreamRelease(stream)
        self.stream = nil
    }

    // MARK: - Event handling

    fileprivate func handlePaths(_ paths: [String], flags: [UInt32]) {
        for (path, flag) in zip(paths, flags) {
            let isCreated  = flag & UInt32(kFSEventStreamEventFlagItemCreated)   != 0
            let isModified = flag & UInt32(kFSEventStreamEventFlagItemModified)  != 0
            let isFile     = flag & UInt32(kFSEventStreamEventFlagItemIsFile)    != 0
            guard isFile, isCreated || isModified else { continue }

            let url = URL(fileURLWithPath: path)
            let ext = url.pathExtension.lowercased()
            guard ContentExtractor.supportedExtensions.contains(ext) else { continue }

            // Always sync path index
            MemoryClient.sendPathEvent(path: path)

            // Try full content extraction in background
            DispatchQueue.global(qos: .background).async {
                guard let result = ContentExtractor.extract(url: url) else { return }
                let score = ImportanceScorer.score(path: path, content: result.text)
                guard score >= ImportanceScorer.ephemeralThreshold else { return }

                if score >= ImportanceScorer.importantThreshold {
                    MemoryClient.promoteToImportant(
                        content: result.text,
                        title: url.lastPathComponent,
                        source: "macos_fs",
                        path: path
                    )
                } else {
                    MemoryClient.sendEphemeral(
                        content: result.text,
                        source: "macos_fs",
                        path: path
                    )
                }
            }
        }
    }
}

// MARK: - C callback bridge

private func fsEventsCallback(
    _ stream: ConstFSEventStreamRef,
    _ clientCallBackInfo: UnsafeMutableRawPointer?,
    _ numEvents: Int,
    _ eventPaths: UnsafeMutableRawPointer,
    _ eventFlags: UnsafePointer<FSEventStreamEventFlags>,
    _ eventIds: UnsafePointer<FSEventStreamEventId>
) {
    guard let info = clientCallBackInfo else { return }
    let watcher = Unmanaged<FSEventsWatcher>.fromOpaque(info).takeUnretainedValue()

    guard let cfPaths = unsafeBitCast(eventPaths, to: NSArray.self) as? [String] else { return }
    let flagsArray = (0..<numEvents).map { UInt32(eventFlags[$0]) }
    watcher.handlePaths(cfPaths, flags: flagsArray)
}
