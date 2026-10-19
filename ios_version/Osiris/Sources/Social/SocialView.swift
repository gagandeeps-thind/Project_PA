import SwiftUI
import OsirisShared

/// Global boards, with ways into local rankings, seasons and communities.
struct SocialView: View {
    @StateObject private var model: Observed<GlobalBoardsViewModel, GlobalBoardsState>
    @EnvironmentObject private var nav: Navigator

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.globalBoards()) { $0.state })
    }

    var body: some View {
        let s = model.state
        List {
            Section {
                HStack {
                    Button("LOCAL & SEASONS") { nav.open(.rankings) }.buttonStyle(.bordered)
                    Button("COMMUNITIES") { nav.open(.clubs) }.buttonStyle(.bordered)
                }
                chips(BoardKind.entries, selected: s.kind, label: \.title) { model.vm.select(kind: $0) }
                chips(BoardPeriod.entries, selected: s.period, label: \.title) { model.vm.select(period: $0) }
                if s.showsExercise {
                    chips(BoardExercise.entries, selected: s.exercise, label: \.title) { model.vm.select(exercise: $0) }
                }
            }
            .listRowBackground(Color.clear)
            board(s.board)
        }
        .scrollContentBackground(.hidden)
        .refreshable { model.vm.refresh() }
        .navigationTitle("SOCIAL")
        .navigationBarTitleDisplayMode(.inline)
        .messages(model)
    }

    @ViewBuilder private func board(_ state: any Loadable) -> some View {
        if let b = state.valueOrNull as? GlobalBoard {
            Section {
                if b.rows.isEmpty { Text("Nobody is on this board yet. One verified session puts you on it.") }
                // Offsets as ids: tied ranks and "Private runner" names repeat.
                ForEach(Array(b.rows.enumerated()), id: \.offset) { _, r in row(b, r) }
                if let me = b.myRow, !b.rows.contains(where: { $0.isMe }) { row(b, me) }
            } header: {
                Text(b.explainer).textCase(nil)
            } footer: {
                Text("\(b.rankedPlayers) ranked players")
            }
            .listRowBackground(Color.clear)
        } else if let failed = state as? LoadableFailed {
            Text(failed.message).foregroundStyle(OsirisColor.error)
        } else {
            ProgressView().frame(maxWidth: .infinity)
        }
    }

    private func row(_ b: GlobalBoard, _ r: BoardRow) -> some View {
        HStack {
            Text("#\(r.rank)").bold().frame(width: 44, alignment: .leading)
            Text(r.isMe ? "\(r.name) (you)" : r.name).foregroundStyle(r.isMe ? OsirisColor.secondary : .primary)
            Spacer()
            Text(b.format(value: r.value))
        }
    }

    private func chips<T: AnyObject & Equatable>(
        _ options: [T], selected: T, label: KeyPath<T, String>, onSelect: @escaping (T) -> Void
    ) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(options.indices, id: \.self) { i in
                    let o = options[i]
                    Button(o[keyPath: label]) { onSelect(o) }
                        .buttonStyle(.bordered)
                        .tint(o == selected ? OsirisColor.primary : OsirisColor.muted)
                }
            }
        }
    }
}
