import SwiftUI
import OsirisShared

/// Accent colors shared by every screen, from the dark FrostMatte palette in the shared core.
/// The app renders dark until every screen reads `FrostPalette`.
enum OsirisColor {
    private static let tokens = FrostMatte.shared.dark
    static let background = Color(argb: tokens.background)
    static let surface = Color(argb: tokens.glassFallback)
    static let primary = Color(argb: tokens.accent)
    static let secondary = Color(argb: tokens.accentAlt)
    static let error = Color(argb: tokens.danger)
    static let success = Color(argb: tokens.success)
    static let warning = Color(argb: tokens.warning)
    static let gold = Color(argb: tokens.gold)
    static let muted = Color(argb: tokens.textSecondary)
    static let faint = Color(argb: tokens.textMuted)

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
