import SwiftUI
import OsirisShared

/// Clubs: the player's own, and public ones to join (by tap, or by group ID and join code).
struct CommunitiesView: View {
    @StateObject private var model: Observed<CommunitiesViewModel, CommunitiesState>
    @EnvironmentObject private var nav: Navigator
    @State private var joinWithCode = false
    @State private var slug = ""
    @State private var code = ""

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.communities()) { $0.state })
    }

    var body: some View {
        let s = model.state
        List {
            section("Your groups", s.mine, empty: "Join your running club, gym, or team to compete together.") { $0 }
            section("Near you", s.discover, empty: "No other public groups in your city yet. Set your city in Settings.") { list in
                list.filter { !$0.isMember }
            }
        }
        .refreshable { model.vm.refresh() }
        .background(OsirisColor.background)
        .navigationTitle("CLUBS & GROUPS")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button { joinWithCode = true } label: { Image(systemName: "key") }
                    .accessibilityLabel("Join with a code")
            }
        }
        .alert("Join a private group", isPresented: $joinWithCode) {
            TextField("Group ID (from the organiser)", text: $slug).textInputAutocapitalization(.never)
            TextField("Join code", text: $code).textInputAutocapitalization(.never)
            Button("JOIN") {
                model.vm.join(slug: slug.trimmingCharacters(in: .whitespaces), joinCode: code.trimmingCharacters(in: .whitespaces))
                slug = ""
                code = ""
            }
            Button("CANCEL", role: .cancel) {}
        }
        .messages(model)
        // Back from a club page: joining or leaving moves it between the lists.
        .onReturn { model.vm.refresh() }
    }

    private func section(
        _ title: String,
        _ state: any Loadable,
        empty: String,
        filter: @escaping ([Community]) -> [Community]
    ) -> some View {
        Section(title.uppercased()) {
            if let failed = state as? LoadableFailed {
                Text(failed.message).foregroundStyle(OsirisColor.error)
            } else if let all = state.valueOrNull as? [Community] {
                let list = filter(all)
                if list.isEmpty { Text(empty) }
                ForEach(list, id: \.slug) { c in
                    Button { nav.open(.club(c.slug)) } label: { tile(c) }
                }
            } else {
                ProgressView().frame(maxWidth: .infinity)
            }
        }
    }

    private func tile(_ c: Community) -> some View {
        HStack(spacing: 12) {
            Text(String(c.name.prefix(1)).uppercased())
                .frame(width: 40, height: 40)
                .background(OsirisColor.brand(c.brandColor), in: Circle())
            VStack(alignment: .leading) {
                HStack(spacing: 6) {
                    Text(c.name).lineLimit(1)
                    if c.verified {
                        Image(systemName: "checkmark.seal.fill").foregroundStyle(OsirisColor.secondary).accessibilityLabel("Verified")
                    }
                }
                Text("\(c.kindLabel)  •  \(c.memberCount) members").font(.subheadline).foregroundStyle(OsirisColor.muted)
            }
            Spacer()
            Image(systemName: "chevron.right").foregroundStyle(OsirisColor.faint)
        }
    }
}
