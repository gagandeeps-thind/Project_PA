import CoreText
import SwiftUI
import UIKit
import OsirisShared

extension Color {
    /// A FrostMatte token, `0xAARRGGBB` as Kotlin `Long`.
    init(argb: Int64) {
        self.init(
            .sRGB,
            red: Double((argb >> 16) & 0xFF) / 255,
            green: Double((argb >> 8) & 0xFF) / 255,
            blue: Double(argb & 0xFF) / 255,
            opacity: Double((argb >> 24) & 0xFF) / 255
        )
    }
}

/// The FrostMatte palette for the current color scheme; the values live in the shared core.
struct FrostPalette {
    let tokens: FrostMatte.Palette

    init(_ scheme: ColorScheme) {
        tokens = FrostMatte.shared.palette(mode: scheme == .dark ? .dark : .light)
    }

    var background: Color { Color(argb: tokens.background) }
    var accentField: Color { Color(argb: tokens.backgroundAccent) }
    var accentFieldAlt: Color { Color(argb: tokens.backgroundAccentAlt) }
    var glassFill: Color { Color(argb: tokens.glassFill) }
    var glassBorder: Color { Color(argb: tokens.glassBorder) }
    var shadow: Color { Color(argb: tokens.shadow) }
    var textPrimary: Color { Color(argb: tokens.textPrimary) }
    var textSecondary: Color { Color(argb: tokens.textSecondary) }
    var textMuted: Color { Color(argb: tokens.textMuted) }
    var accent: Color { Color(argb: tokens.accent) }
    var success: Color { Color(argb: tokens.success) }
}

/// Matte backdrop: the palette background with two soft accent fields and no gloss.
struct FrostBackground: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = FrostPalette(scheme)
        GeometryReader { geo in
            let size = max(geo.size.width, geo.size.height)
            ZStack {
                palette.background
                RadialGradient(colors: [palette.accentField, .clear], center: UnitPoint(x: 0.1, y: 0.05), startRadius: 0, endRadius: size * 0.7)
                RadialGradient(colors: [palette.accentFieldAlt, .clear], center: UnitPoint(x: 0.95, y: 0.85), startRadius: 0, endRadius: size * 0.6)
            }
        }
        .ignoresSafeArea()
    }
}

/// Frosted glass: system material blur, translucent fill, 1 pt hairline, soft diffuse shadow.
struct FrostSurface: ViewModifier {
    @Environment(\.colorScheme) private var scheme
    var radius: CGFloat = CGFloat(FrostMatte.Radius.shared.MEDIUM)

    func body(content: Content) -> some View {
        let palette = FrostPalette(scheme)
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
        content
            .background(palette.glassFill, in: shape)
            .background(.ultraThinMaterial, in: shape)
            .overlay(shape.stroke(palette.glassBorder, lineWidth: CGFloat(FrostMatte.shared.BORDER_WIDTH)))
            .shadow(color: palette.shadow, radius: CGFloat(FrostMatte.Shadow.shared.RADIUS) / 2, y: CGFloat(FrostMatte.Shadow.shared.OFFSET_Y))
    }
}

extension View {
    func frost(radius: CGFloat = CGFloat(FrostMatte.Radius.shared.MEDIUM)) -> some View {
        modifier(FrostSurface(radius: radius))
    }

    /// A padded FrostMatte card.
    func frostCard() -> some View {
        padding(CGFloat(FrostMatte.Spacing.shared.L)).frame(maxWidth: .infinity, alignment: .leading).frost()
    }
}

/// Manrope (display and body) and Geist Mono (small labels), bundled with `UIAppFonts`. Both are
/// variable fonts, so a weight is set on the `wght` axis, as Android does with `FontVariation`.
enum FrostFont {
    /// The `wght` variation axis tag.
    private static let weightAxis = 0x7767_6874

    static func manrope(_ style: FrostMatte.TextStyle, weight: Int? = nil) -> Font {
        variable("Manrope", style: style, weight: weight)
    }

    static func mono(_ style: FrostMatte.TextStyle, weight: Int = 600) -> Font {
        variable("Geist Mono", style: style, weight: weight)
    }

    /// Hero stays at its token size, as on Android; every other style follows Dynamic Type.
    private static func variable(_ family: String, style: FrostMatte.TextStyle, weight: Int?) -> Font {
        let descriptor = UIFontDescriptor(fontAttributes: [
            .family: family,
            UIFontDescriptor.AttributeName(rawValue: kCTFontVariationAttribute as String): [weightAxis: weight ?? Int(style.weight)],
        ])
        let font = UIFont(descriptor: descriptor, size: CGFloat(style.size))
        return Font(style == .hero ? font : UIFontMetrics.default.scaledFont(for: font))
    }
}

/// The one focal number of a screen: 72 pt Manrope ExtraBold, tight tracking. The unit and the
/// labels around it stay small and muted so nothing competes with it.
struct HeroMetric: View {
    let value: String
    var unit: String? = nil
    var label: String? = nil
    var caption: String? = nil
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = FrostPalette(scheme)
        let hero = FrostMatte.TextStyle.hero
        VStack(alignment: .leading, spacing: 0) {
            if let label {
                Text(label.uppercased()).font(FrostFont.mono(.caption)).foregroundStyle(palette.textMuted)
            }
            HStack(alignment: .lastTextBaseline, spacing: 8) {
                Text(value)
                    .font(FrostFont.manrope(hero))
                    .tracking(CGFloat(hero.size * FrostMatte.shared.HERO_TRACKING_EM))
                    .foregroundStyle(palette.textPrimary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
                if let unit {
                    Text(unit).font(FrostFont.manrope(.headline, weight: 700)).foregroundStyle(palette.textMuted)
                }
            }
            if let caption {
                Text(caption).font(FrostFont.manrope(.callout)).foregroundStyle(palette.textSecondary)
            }
        }
        .accessibilityElement(children: .combine)
    }
}
