import SwiftUI
import UIKit
import OsirisShared

/// Shows a shared `Loadable`: a spinner, the failure with TRY AGAIN, or the content.
struct LoadableContent<T, Content: View>: View {
    let state: any Loadable
    let onRetry: () -> Void
    @ViewBuilder let content: (T) -> Content

    var body: some View {
        if let value = state.valueOrNull as? T {
            content(value)
        } else if let failed = state as? LoadableFailed {
            VStack(spacing: 12) {
                Text(failed.message).foregroundStyle(OsirisColor.error).multilineTextAlignment(.center)
                if failed.canRetry { Button("TRY AGAIN", action: onRetry).buttonStyle(.bordered) }
            }
            .padding(24)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}

/// An empty list: an icon, a line saying so, and what to do about it.
struct EmptyState: View {
    let icon: String
    let title: String
    var detail: String?
    var actionLabel: String?
    var action: (() -> Void)?

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: icon).font(.system(size: 48)).foregroundStyle(.white.opacity(0.38))
            Text(title).multilineTextAlignment(.center)
            if let detail { Text(detail).foregroundStyle(OsirisColor.faint).multilineTextAlignment(.center) }
            if let actionLabel, let action {
                Button(actionLabel, action: action).buttonStyle(.borderedProminent).padding(.top, 4)
            }
        }
        .padding(32)
        .frame(maxWidth: .infinity)
    }
}

/// A small rounded label.
struct Chip: View {
    let label: String
    let color: Color

    var body: some View {
        Text(label)
            .font(.caption2)
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(color.opacity(0.15), in: RoundedRectangle(cornerRadius: 8))
    }
}

/// A label and value on one line, labels aligned in a column.
struct TermRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .top) {
            Text(label).foregroundStyle(OsirisColor.faint).frame(width: 130, alignment: .leading)
            Text(value).frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 3)
    }
}

/// An uppercase section label.
struct SectionLabel: View {
    let text: String

    var body: some View {
        Text(text.uppercased()).font(.caption).kerning(1.2).foregroundStyle(OsirisColor.muted)
    }
}

/// Text handed to the share sheet; identifiable so `.sheet(item:)` can present it.
struct SharedText: Identifiable {
    let id = UUID()
    let text: String
}

/// The system share sheet for one piece of text. [onDone] says whether it was shared.
struct ShareSheet: UIViewControllerRepresentable {
    let text: String
    var onDone: (Bool) -> Void = { _ in }

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: [text], applicationActivities: nil)
        controller.completionWithItemsHandler = { _, completed, _, _ in onDone(completed) }
        return controller
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}

extension View {
    /// Presents a view model's `ShareRequest` and reports back once it is shared or cancelled.
    func shareSheet(_ request: ShareRequest?, onDone: @escaping (Bool) -> Void) -> some View {
        sheet(isPresented: Binding(get: { request != nil }, set: { if !$0 { onDone(false) } })) {
            if let request { ShareSheet(text: request.text, onDone: onDone) }
        }
    }

    /// Runs [action] each time the screen shows again after the first time (back from a pushed
    /// screen), since the data may have changed there; the first load is the view model's own.
    func onReturn(_ action: @escaping () -> Void) -> some View {
        modifier(ReturnModifier(action: action))
    }

    /// A text-entry alert, the iOS counterpart of the Android TextInputDialog.
    func textInputAlert(
        _ title: String,
        isPresented: Binding<Bool>,
        message: String? = nil,
        label: String,
        text: Binding<String>,
        confirm: String,
        dismiss: String,
        secure: Bool = false,
        destructive: Bool = false,
        keyboard: UIKeyboardType = .default,
        onConfirm: @escaping (String) -> Void,
        onDismiss: @escaping () -> Void
    ) -> some View {
        alert(title, isPresented: isPresented) {
            if secure { SecureField(label, text: text) } else { TextField(label, text: text).keyboardType(keyboard) }
            Button(confirm, role: destructive ? .destructive : nil) {
                // Passwords are sent as typed; other entries lose stray spaces.
                let value = text.wrappedValue
                onConfirm(secure ? value : value.trimmingCharacters(in: .whitespacesAndNewlines))
            }
            Button(dismiss, role: .cancel, action: onDismiss)
        } message: {
            if let message { Text(message) }
        }
    }
}

private struct ReturnModifier: ViewModifier {
    let action: () -> Void
    @State private var appeared = false

    func body(content: Content) -> some View {
        content.onAppear {
            if appeared { action() } else { appeared = true }
        }
    }
}

/// Opens this app's page in the Settings app, where a refused permission can be turned on.
func openAppSettings() {
    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
}
