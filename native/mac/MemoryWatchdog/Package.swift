// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MemoryWatchdog",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "MemoryWatchdog",
            path: "Sources/MemoryWatchdog",
            swiftSettings: [
                .unsafeFlags(["-framework", "AppKit",
                              "-framework", "PDFKit",
                              "-framework", "AVFoundation"])
            ]
        )
    ]
)
