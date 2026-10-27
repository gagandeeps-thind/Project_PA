import CoreMotion
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
    var glassSheen: Color { Color(argb: tokens.glassSheen) }
    var glassBorder: Color { Color(argb: tokens.glassBorder) }
    var shadow: Color { Color(argb: tokens.shadow) }
    var textPrimary: Color { Color(argb: tokens.textPrimary) }
    var textSecondary: Color { Color(argb: tokens.textSecondary) }
    var textMuted: Color { Color(argb: tokens.textMuted) }
    var accent: Color { Color(argb: tokens.accent) }
    var onAccent: Color { Color(argb: tokens.onAccent) }
    var success: Color { Color(argb: tokens.success) }
}

/// The light, fixed in the world: gravity says which way is down and every pane's shadow falls that
/// way, so tilting the phone moves shadows and rims. Stays at rest when Reduce Motion is on.
final class Light: ObservableObject {
    static let shared = Light()

    @Published private(set) var fall = CGVector(dx: CGFloat(FrostMatte.Depth.shared.REST.x), dy: CGFloat(FrostMatte.Depth.shared.REST.y))
    private let motion = CMMotionManager()
    private var watchers = 0

    /// Low-pass weight per sample, and the smallest change worth a redraw.
    private let smoothing: CGFloat = 0.2
    private let deadband: CGFloat = 0.006

    func start() {
        watchers += 1
        guard watchers == 1, motion.isDeviceMotionAvailable, !UIAccessibility.isReduceMotionEnabled else { return }
        motion.deviceMotionUpdateInterval = 1.0 / 30
        motion.startDeviceMotionUpdates(to: .main) { [weak self] data, _ in
            guard let self, let g = data?.gravity else { return }
            // Core Motion's gravity points at the earth with y up the screen; shadows want y down.
            let target = FrostMatte.Depth.shared.fall(downX: Float(g.x), downY: Float(-g.y))
            let x = self.fall.dx + (CGFloat(target.x) - self.fall.dx) * self.smoothing
            let y = self.fall.dy + (CGFloat(target.y) - self.fall.dy) * self.smoothing
            if abs(x - self.fall.dx) + abs(y - self.fall.dy) > self.deadband { self.fall = CGVector(dx: x, dy: y) }
        }
    }

    func stop() {
        watchers = max(0, watchers - 1)
        if watchers == 0 { motion.stopDeviceMotionUpdates() }
    }
}

/// The floor of the Z-axis: slate with a pool of light in the top left. It runs the [Light] while shown.
struct FrostBackground: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = FrostPalette(scheme)
        GeometryReader { geo in
            let size = max(geo.size.width, geo.size.height)
            ZStack {
                palette.background
                RadialGradient(
                    stops: [
                        .init(color: palette.accentField, location: 0),
                        .init(color: palette.background, location: 0.6),
                        .init(color: palette.accentFieldAlt, location: 1),
                    ],
                    center: UnitPoint(x: 0.2, y: 0),
                    startRadius: 0,
                    endRadius: size * 1.1
                )
            }
        }
        .ignoresSafeArea()
        .onAppear { Light.shared.start() }
        .onDisappear { Light.shared.stop() }
    }
}

/// A glass pane [height] points above the floor: blur, a sheen brighter at the top, a rim bright on
/// the edge facing the light, an ambient and a contact shadow falling with the light and, for floating
/// chrome, a crisp [ring].
struct FrostSurface: ViewModifier {
    @Environment(\.colorScheme) private var scheme
    @ObservedObject private var light = Light.shared
    var radius: CGFloat = CGFloat(FrostMatte.Radius.shared.MEDIUM)
    var height: CGFloat = CGFloat(FrostMatte.Depth.shared.CARD)
    var ring = false
    var fill: Color?

    func body(content: Content) -> some View {
        let palette = FrostPalette(scheme)
        let depth = FrostMatte.Depth.shared
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
        let fall = light.fall
        let rim = palette.glassBorder
        content
            .background(LinearGradient(colors: [palette.glassSheen, palette.glassFill], startPoint: .top, endPoint: .bottom), in: shape)
            .background(fill ?? .clear, in: shape)
            .background(.ultraThinMaterial, in: shape)
            .overlay(
                shape.strokeBorder(
                    LinearGradient(
                        stops: [
                            .init(color: rim, location: 0),
                            .init(color: rim.opacity(0.12), location: 0.45),
                            .init(color: .clear, location: 1),
                        ],
                        startPoint: UnitPoint(x: 0.5 - fall.dx / 2, y: 0.5 - fall.dy / 2),
                        endPoint: UnitPoint(x: 0.5 + fall.dx / 2, y: 0.5 + fall.dy / 2)
                    ),
                    lineWidth: CGFloat(FrostMatte.shared.BORDER_WIDTH)
                )
            )
            .overlay(shape.inset(by: -1).stroke(palette.shadow, lineWidth: 1).opacity(ring ? 1 : 0))
            .shadow(
                color: palette.shadow.opacity(Double(depth.CONTACT_ALPHA)),
                radius: CGFloat(depth.CONTACT_BLUR) / 2,
                x: fall.dx * height * CGFloat(depth.CONTACT_SHARE),
                y: fall.dy * height * CGFloat(depth.CONTACT_SHARE)
            )
            .shadow(
                color: palette.shadow.opacity(Double(depth.AMBIENT_ALPHA)),
                radius: height * CGFloat(depth.AMBIENT_BLUR_PER_HEIGHT) / 2,
                x: fall.dx * height,
                y: fall.dy * height
            )
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

/// Manrope, bundled with `UIAppFonts`. It is a variable font, so a weight is set on the `wght` axis,
/// as Android does with `FontVariation`. Every face uses tabular figures.
enum FrostFont {
    /// The `wght` variation axis tag.
    private static let weightAxis = 0x7767_6874

    static func manrope(_ style: FrostMatte.TextStyle, weight: Int? = nil) -> Font {
        let font = uiFont(size: CGFloat(style.size), weight: weight ?? Int(style.weight))
        // Hero stays at its token size, as on Android; every other style follows Dynamic Type.
        return Font(style == .hero ? font : UIFontMetrics.default.scaledFont(for: font)).monospacedDigit()
    }

    static func uiFont(size: CGFloat, weight: Int) -> UIFont {
        let descriptor = UIFontDescriptor(fontAttributes: [
            .family: "Manrope",
            UIFontDescriptor.AttributeName(rawValue: kCTFontVariationAttribute as String): [weightAxis: weight],
        ])
        return UIFont(descriptor: descriptor, size: size)
    }
}

extension Font {
    /// Manrope in place of a system text style: the same size, weight and Dynamic Type scaling.
    static func manrope(_ style: Font.TextStyle) -> Font {
        let (size, weight, metrics): (CGFloat, Int, UIFont.TextStyle) = switch style {
        case .largeTitle: (34, 800, .largeTitle)
        case .title: (28, 700, .title1)
        case .title2: (22, 700, .title2)
        case .title3: (20, 600, .title3)
        case .headline: (17, 600, .headline)
        case .subheadline: (15, 500, .subheadline)
        case .callout: (16, 500, .callout)
        case .footnote: (13, 500, .footnote)
        case .caption: (12, 600, .caption1)
        case .caption2: (11, 600, .caption2)
        default: (17, 400, .body)
        }
        return Font(UIFontMetrics(forTextStyle: metrics).scaledFont(for: FrostFont.uiFont(size: size, weight: weight))).monospacedDigit()
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
                Text(label).font(FrostFont.manrope(.caption)).foregroundStyle(palette.textMuted)
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

/// A chunky physical key: the face is lit from the top and stands on a darker base; pressing shrinks
/// it and sinks it onto the base. Primary keys are ember, the rest raised slate.
struct KeyButtonStyle: ButtonStyle {
    var primary = true

    func makeBody(configuration: Configuration) -> some View {
        KeyFace(configuration: configuration, primary: primary)
    }
}

extension ButtonStyle where Self == KeyButtonStyle {
    /// The screen's main action.
    static var key: KeyButtonStyle { KeyButtonStyle() }
    /// A secondary action.
    static var raised: KeyButtonStyle { KeyButtonStyle(primary: false) }
}

private struct KeyFace: View {
    let configuration: ButtonStyleConfiguration
    let primary: Bool
    @Environment(\.isEnabled) private var enabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = FrostPalette(scheme)
        let pressed = configuration.isPressed && enabled
        let depth = CGFloat(FrostMatte.Depth.shared.KEY)
        let shape = RoundedRectangle(cornerRadius: 16, style: .continuous)
        let face = primary
            ? [Color(argb: FrostMatte.shared.ACCENT_TOP), palette.accent]
            : [Color(argb: 0xFF2C3039), Color(argb: 0xFF21242B)]
        let base = primary ? Color(argb: FrostMatte.shared.ACCENT_BASE) : Color(argb: 0xFF0E1014)
        configuration.label
            .font(.manrope(.body).weight(.heavy))
            .foregroundStyle(primary ? palette.onAccent : palette.textPrimary)
            .padding(.horizontal, 22)
            .padding(.vertical, 12)
            .frame(minHeight: CGFloat(FrostMatte.shared.MIN_TOUCH_TARGET))
            .background(LinearGradient(colors: face, startPoint: .top, endPoint: .bottom), in: shape)
            .overlay(
                shape.inset(by: 0.5).stroke(
                    LinearGradient(colors: [.white.opacity(primary ? 0.4 : 0.14), .clear], startPoint: .top, endPoint: .center),
                    lineWidth: 1
                )
            )
            .offset(y: pressed ? depth : 0)
            // The base stays put while the face travels down onto it.
            .background(shape.fill(base).offset(y: depth))
            .shadow(color: palette.shadow.opacity(0.5), radius: pressed ? 2 : 6, y: pressed ? depth : depth * 2)
            .scaleEffect(pressed ? CGFloat(FrostMatte.Depth.shared.PRESS_SCALE) : 1)
            .opacity(enabled ? 1 : 0.4)
            .padding(.bottom, depth)
            .animation(reduceMotion ? nil : .spring(response: 0.22, dampingFraction: 0.6), value: pressed)
    }
}

/// A floating, pill-shaped HUD readout, used for messages instead of a flat banner.
struct HudPill: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.manrope(.subheadline))
            .multilineTextAlignment(.center)
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .modifier(FrostSurface(
                radius: CGFloat(FrostMatte.Radius.shared.PILL),
                height: CGFloat(FrostMatte.Depth.shared.FLOAT),
                ring: true,
                fill: Color(argb: 0xF2252932)
            ))
    }
}
