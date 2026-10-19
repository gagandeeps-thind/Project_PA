import SwiftUI
import OsirisShared

/// The Osiris dark palette, the same values as the Android and Flutter themes.
enum OsirisColor {
    static let background = Color(red: 0x12 / 255, green: 0x12 / 255, blue: 0x12 / 255)
    static let surface = Color(red: 0x1E / 255, green: 0x1E / 255, blue: 0x1E / 255)
    static let primary = Color(red: 0x9D / 255, green: 0x4E / 255, blue: 0xDD / 255)
    static let secondary = Color(red: 0x03 / 255, green: 0xDA / 255, blue: 0xC6 / 255)
    static let error = Color(red: 0xCF / 255, green: 0x66 / 255, blue: 0x79 / 255)
    static let success = Color(red: 0x4C / 255, green: 0xAF / 255, blue: 0x50 / 255)
    static let warning = Color(red: 0xFF / 255, green: 0xC1 / 255, blue: 0x07 / 255)
    static let gold = Color(red: 0xFD / 255, green: 0xD8 / 255, blue: 0x35 / 255)
    static let muted = Color.white.opacity(0.70)
    static let faint = Color.white.opacity(0.60)

    /// A club's brand colour from `#RRGGBB`, or the app colour when missing or malformed.
    static func brand(_ hex: String?) -> Color {
        guard var digits = hex else { return primary }
        if digits.hasPrefix("#") { digits.removeFirst() }
        guard digits.count == 6, let v = UInt32(digits, radix: 16) else { return primary }
        return Color(red: Double((v >> 16) & 0xFF) / 255, green: Double((v >> 8) & 0xFF) / 255, blue: Double(v & 0xFF) / 255)
    }
}

/// Shows a view model message as a banner at the top, then reports it shown.
struct MessageBanner: ViewModifier {
    let text: String?
    let onShown: () -> Void

    func body(content: Content) -> some View {
        content.overlay(alignment: .top) {
            if let text {
                Text(text)
                    .padding(12)
                    .frame(maxWidth: .infinity)
                    .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 12))
                    .padding()
                    .task(id: text) {
                        try? await Task.sleep(nanoseconds: 3_000_000_000)
                        onShown()
                    }
            }
        }
    }
}

extension View {
    /// The view model's messages as banners.
    func messages<VM: SharedViewModel, S>(_ model: Observed<VM, S>) -> some View {
        modifier(MessageBanner(text: model.message?.text, onShown: { model.messageShown() }))
    }
}
