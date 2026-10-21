import SwiftUI
import OsirisShared

/// Live support chat.
struct SupportChatView: View {
    @StateObject private var model: Observed<SupportChatViewModel, SupportChatState>
    @State private var draft = ""

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.supportChat()) { $0.state })
    }

    var body: some View {
        let s = model.state
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(Array(s.lines.enumerated()), id: \.offset) { i, line in
                            HStack {
                                if line.mine { Spacer(minLength: 48) }
                                Text(line.text)
                                    .padding(12)
                                    .background(
                                        (line.mine ? OsirisColor.primary.opacity(0.32) : OsirisColor.faint.opacity(0.16)),
                                        in: RoundedRectangle(cornerRadius: 12)
                                    )
                                if !line.mine { Spacer(minLength: 48) }
                            }
                            .id(i)
                        }
                    }
                    .padding(16)
                }
                .onChange(of: s.lines.count) { count in
                    if count > 0 { withAnimation { proxy.scrollTo(count - 1, anchor: .bottom) } }
                }
            }
            composer(s)
        }
        .navigationTitle("SUPPORT")
        .navigationBarTitleDisplayMode(.inline)
        .messages(model)
    }

    @ViewBuilder private func composer(_ s: SupportChatState) -> some View {
        switch s.status {
        case .open:
            HStack {
                TextField("Message", text: $draft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .onChange(of: draft) { value in
                        let limit = Int(SupportOutgoing.companion.MAX_LENGTH)
                        if value.count > limit { draft = String(value.prefix(limit)) }
                    }
                Button { if model.vm.send(text: draft) { draft = "" } } label: { Image(systemName: "paperplane.fill") }
                    .accessibilityLabel("Send")
                    .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(8)
        case .closed:
            HStack {
                Text(s.error ?? "Chat ended.").foregroundStyle(OsirisColor.muted)
                Spacer()
                Button("RECONNECT") { model.vm.connect() }.buttonStyle(.bordered)
            }
            .padding(16)
        default:
            Text("Connecting…").foregroundStyle(OsirisColor.faint).padding(16)
        }
    }
}
