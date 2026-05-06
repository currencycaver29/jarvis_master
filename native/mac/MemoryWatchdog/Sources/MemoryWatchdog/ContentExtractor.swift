import Foundation
import PDFKit
import AVFoundation

struct ExtractionResult {
    let text: String
    let truncated: Bool
}

private let MAX_CHARS = 8_000

enum ContentExtractor {

    static let supportedExtensions: Set<String> = [
        "pdf", "docx", "doc", "txt", "md", "pages",
        "mp3", "mp4", "mov", "png", "jpg", "jpeg", "html", "htm",
    ]

    static func extract(url: URL) -> ExtractionResult? {
        let ext = url.pathExtension.lowercased()
        switch ext {
        case "pdf":              return extractPDF(url: url)
        case "docx", "doc":      return extractDOCX(url: url)
        case "txt", "md":        return extractPlainText(url: url)
        case "html", "htm":      return extractHTML(url: url)
        case "mp3", "mp4", "mov":return extractAVMetadata(url: url)
        case "png", "jpg", "jpeg":
            // No text content — just send path event
            return ExtractionResult(text: "Image: \(url.lastPathComponent)", truncated: false)
        default:
            return nil
        }
    }

    // MARK: - PDF

    private static func extractPDF(url: URL) -> ExtractionResult? {
        guard let doc = PDFDocument(url: url) else { return nil }
        var parts: [String] = []
        for i in 0..<doc.pageCount {
            if let page = doc.page(at: i), let str = page.string {
                parts.append(str)
            }
        }
        let full = parts.joined(separator: "\n")
        if full.isEmpty { return nil }
        if full.count > MAX_CHARS {
            return ExtractionResult(text: String(full.prefix(MAX_CHARS)), truncated: true)
        }
        return ExtractionResult(text: full, truncated: false)
    }

    // MARK: - DOCX (unzip word/document.xml, strip tags)

    private static func extractDOCX(url: URL) -> ExtractionResult? {
        guard let archive = try? Data(contentsOf: url) else { return nil }
        // Quick check: DOCX is a ZIP; find "word/document.xml" by scanning for the entry name
        guard let xmlData = extractZipEntry(zipData: archive, entryName: "word/document.xml") else { return nil }
        let xmlStr = String(data: xmlData, encoding: .utf8) ?? ""
        // Strip all XML tags — leave text runs separated by spaces
        let stripped = xmlStr.replacingOccurrences(of: "<[^>]+>", with: " ",
                                                    options: .regularExpression)
            .components(separatedBy: .whitespaces)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
        if stripped.isEmpty { return nil }
        if stripped.count > MAX_CHARS {
            return ExtractionResult(text: String(stripped.prefix(MAX_CHARS)), truncated: true)
        }
        return ExtractionResult(text: stripped, truncated: false)
    }

    /// Minimal ZIP entry reader (no external dependencies).
    private static func extractZipEntry(zipData: Data, entryName: String) -> Data? {
        // Local file header signature: PK\x03\x04
        let sig: [UInt8] = [0x50, 0x4B, 0x03, 0x04]
        var offset = 0
        let bytes = [UInt8](zipData)
        while offset + 30 < bytes.count {
            guard bytes[offset..<offset+4].elementsEqual(sig) else {
                offset += 1; continue
            }
            let compression = UInt16(bytes[offset+8]) | (UInt16(bytes[offset+9]) << 8)
            let compressedSize = Int(UInt32(bytes[offset+18]) | (UInt32(bytes[offset+19]) << 8)
                | (UInt32(bytes[offset+20]) << 16) | (UInt32(bytes[offset+21]) << 24))
            let fnLen  = Int(UInt16(bytes[offset+26]) | (UInt16(bytes[offset+27]) << 8))
            let extLen = Int(UInt16(bytes[offset+28]) | (UInt16(bytes[offset+29]) << 8))
            let dataStart = offset + 30 + fnLen + extLen
            if let name = String(bytes: bytes[(offset+30)..<(offset+30+fnLen)], encoding: .utf8),
               name == entryName {
                guard dataStart + compressedSize <= bytes.count else { return nil }
                let entryData = Data(bytes[dataStart..<dataStart+compressedSize])
                // compression == 0 → stored; 8 → deflate (skip for simplicity, return raw)
                if compression == 0 { return entryData }
                // For deflate, use NSData decompression
                return try? (entryData as NSData).decompressed(using: .zlib) as Data?
            }
            offset = dataStart + compressedSize
        }
        return nil
    }

    // MARK: - Plain text

    private static func extractPlainText(url: URL) -> ExtractionResult? {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return nil }
        if text.count > MAX_CHARS {
            return ExtractionResult(text: String(text.prefix(MAX_CHARS)), truncated: true)
        }
        return ExtractionResult(text: text, truncated: false)
    }

    // MARK: - HTML

    private static func extractHTML(url: URL) -> ExtractionResult? {
        guard let html = try? String(contentsOf: url, encoding: .utf8) else { return nil }
        let stripped = html.replacingOccurrences(of: "<[^>]+>", with: " ",
                                                  options: .regularExpression)
            .components(separatedBy: .whitespaces).filter { !$0.isEmpty }.joined(separator: " ")
        if stripped.isEmpty { return nil }
        if stripped.count > MAX_CHARS {
            return ExtractionResult(text: String(stripped.prefix(MAX_CHARS)), truncated: true)
        }
        return ExtractionResult(text: stripped, truncated: false)
    }

    // MARK: - AV metadata

    private static func extractAVMetadata(url: URL) -> ExtractionResult? {
        let asset = AVURLAsset(url: url)
        var parts: [String] = ["File: \(url.lastPathComponent)"]
        let meta = asset.commonMetadata
        for item in meta {
            if let key = item.commonKey?.rawValue, let value = item.value as? String {
                parts.append("\(key): \(value)")
            }
        }
        let duration = asset.duration
        if duration.isValid && !duration.isIndefinite {
            let secs = Int(CMTimeGetSeconds(duration))
            parts.append("Duration: \(secs / 60)m \(secs % 60)s")
        }
        return ExtractionResult(text: parts.joined(separator: "\n"), truncated: false)
    }
}
