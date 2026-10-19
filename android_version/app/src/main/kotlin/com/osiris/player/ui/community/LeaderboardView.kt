package com.osiris.player.ui.community

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.Leaderboard
import com.osiris.shared.domain.model.LeaderboardRow

/** A leaderboard list. Players who have not opted in arrive from the server as "Private runner". */
@Composable
fun LeaderboardView(board: Leaderboard, compact: Boolean = false) {
    val rows = if (compact) board.rows.take(10) else board.rows
    Column {
        if (!compact) Text(board.title.uppercase(), color = OsirisColors.Muted, fontSize = 12.sp, letterSpacing = 1.2.sp)
        if (rows.isEmpty()) {
            Text("Nobody has scored yet this week. A short walk puts you on the board.", Modifier.padding(vertical = 12.dp))
        }
        rows.forEach { LeaderRow(it) }
        val me = board.myRow
        if (rows.none { it.isMe } && me != null) {
            HorizontalDivider()
            LeaderRow(me)
        }
        Text(board.scoring, color = OsirisColors.Faint, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))
    }
}

@Composable
private fun LeaderRow(r: LeaderboardRow) {
    ListItem(
        leadingContent = { Text("#${r.rank}", fontWeight = FontWeight.Bold, modifier = Modifier.width(36.dp)) },
        headlineContent = { Text(if (r.isMe) "${r.name} (you)" else r.name, color = if (r.isMe) OsirisColors.Secondary else Color.Unspecified) },
        supportingContent = { Text("${r.activeDays} active days  •  ${Format.fixed(r.distanceKm, 1)} km") },
        trailingContent = { Text("${r.points} pts") },
        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
    )
}

/** A club's brand colour from `#RRGGBB`, or the app colour when missing or malformed. */
fun brandColor(hex: String?): Color {
    val digits = hex?.removePrefix("#")?.takeIf { it.length == 6 } ?: return OsirisColors.Primary
    return digits.toLongOrNull(16)?.let { Color(0xFF000000 or it) } ?: OsirisColors.Primary
}
