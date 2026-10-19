import SwiftUI
import OsirisShared

/// A leaderboard list. Players who have not opted in arrive from the server as "Private runner".
struct LeaderboardView: View {
    let board: Leaderboard
    var compact = false

    var body: some View {
        let rows = compact ? Array(board.rows.prefix(10)) : board.rows
        VStack(alignment: .leading, spacing: 4) {
            if !compact { SectionLabel(text: board.title) }
            if rows.isEmpty {
                Text("Nobody has scored yet this week. A short walk puts you on the board.").padding(.vertical, 12)
            }
            ForEach(rows, id: \.rank) { row($0) }
            if !rows.contains(where: { $0.isMe }), let me = board.myRow {
                Divider()
                row(me)
            }
            Text(board.scoring).font(.caption).foregroundStyle(OsirisColor.faint).padding(.top, 8)
        }
    }

    private func row(_ r: LeaderboardRow) -> some View {
        HStack {
            Text("#\(r.rank)").fontWeight(.bold).frame(width: 40, alignment: .leading)
            VStack(alignment: .leading) {
                Text(r.isMe ? "\(r.name) (you)" : r.name).foregroundStyle(r.isMe ? OsirisColor.secondary : .white)
                Text("\(r.activeDays) active days  •  \(Format.shared.fixed(value: r.distanceKm, decimals: 1)) km")
                    .font(.subheadline).foregroundStyle(OsirisColor.muted)
            }
            Spacer()
            Text("\(r.points) pts")
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}
