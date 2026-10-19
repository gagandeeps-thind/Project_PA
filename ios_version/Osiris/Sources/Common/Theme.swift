import SwiftUI

/// The Osiris dark palette, the same values as the Android and Flutter themes.
enum OsirisColor {
    static let background = Color(red: 0x12 / 255, green: 0x12 / 255, blue: 0x12 / 255)
    static let surface = Color(red: 0x1E / 255, green: 0x1E / 255, blue: 0x1E / 255)
    static let primary = Color(red: 0x9D / 255, green: 0x4E / 255, blue: 0xDD / 255)
    static let secondary = Color(red: 0x03 / 255, green: 0xDA / 255, blue: 0xC6 / 255)
    static let error = Color(red: 0xCF / 255, green: 0x66 / 255, blue: 0x79 / 255)
    static let success = Color(red: 0x4C / 255, green: 0xAF / 255, blue: 0x50 / 255)
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
                    .task {
                        try? await Task.sleep(nanoseconds: 3_000_000_000)
                        onShown()
                    }
            }
        }
    }
}
