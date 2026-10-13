import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../api/growth_models.dart';
import '../providers.dart';
import '../theme.dart';

final _localBoardProvider = FutureProvider.autoDispose<Leaderboard>((ref) async {
  return Leaderboard.fromJson(await ref.read(apiClientProvider).getLocalLeaderboard());
});

final _seasonsProvider = FutureProvider.autoDispose<List<Season>>((ref) async {
  final rows = await ref.read(apiClientProvider).getSeasons();
  return rows.map((r) => Season.fromJson(r as Map<String, dynamic>)).toList();
});

/// This week's city ranking and the current city season.
class RankingsScreen extends ConsumerWidget {
  const RankingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final board = ref.watch(_localBoardProvider);
    final seasons = ref.watch(_seasonsProvider);
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('RANKINGS'),
          bottom: const TabBar(tabs: [Tab(text: 'THIS WEEK'), Tab(text: 'SEASON')]),
        ),
        body: TabBarView(children: [
          RefreshIndicator(
            onRefresh: () async => ref.invalidate(_localBoardProvider),
            child: ListView(padding: const EdgeInsets.all(16), children: [
              board.when(
                loading: () => const LinearProgressIndicator(),
                error: (e, _) => _CityPrompt(message: ApiError.getMessage(e)),
                data: (b) => LeaderboardView(board: b),
              ),
            ]),
          ),
          RefreshIndicator(
            onRefresh: () async => ref.invalidate(_seasonsProvider),
            child: ListView(padding: const EdgeInsets.all(16), children: [
              ...seasons.when(
                loading: () => [const LinearProgressIndicator()],
                error: (e, _) => [Text(ApiError.getMessage(e))],
                data: (list) => list.isEmpty
                    ? [const Text('No season in your city right now. Set your city in Settings to see local seasons.')]
                    : list.map((s) => _SeasonCard(season: s)).toList(),
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}

class _CityPrompt extends StatelessWidget {
  final String message;

  const _CityPrompt({required this.message});

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(message),
      const SizedBox(height: 12),
      OutlinedButton(
        onPressed: () => Navigator.of(context).pushNamed('/settings'),
        child: const Text('SET MY CITY'),
      ),
    ]);
  }
}

class _SeasonCard extends ConsumerStatefulWidget {
  final Season season;

  const _SeasonCard({required this.season});

  @override
  ConsumerState<_SeasonCard> createState() => _SeasonCardState();
}

class _SeasonCardState extends ConsumerState<_SeasonCard> {
  Map<String, dynamic>? _board;
  bool _entered = false;

  @override
  void initState() {
    super.initState();
    _entered = widget.season.entered;
    _loadBoard();
  }

  Future<void> _loadBoard() async {
    try {
      final data = await ref.read(apiClientProvider).getSeasonLeaderboard(widget.season.slug);
      if (mounted) setState(() => _board = data);
    } catch (_) {}
  }

  Future<void> _join() async {
    try {
      await ref.read(apiClientProvider).joinSeason(widget.season.slug);
      if (mounted) setState(() => _entered = true);
      await _loadBoard();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(ApiError.getMessage(e)), backgroundColor: OsirisTheme.error),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.season;
    final daysLeft = s.endsAt.difference(DateTime.now()).inDays;
    final players = _board == null ? null : Leaderboard.fromJson(_board!['players'] as Map<String, dynamic>);
    final clubs = (_board?['communities'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(s.name, style: Theme.of(context).textTheme.titleLarge),
          Text('${s.status == 'upcoming' ? 'Starts soon' : '$daysLeft days left'}  •  ${s.participants} taking part',
              style: const TextStyle(color: Colors.white70)),
          if (s.description != null) ...[const SizedBox(height: 8), Text(s.description!)],
          const SizedBox(height: 12),
          if (!_entered)
            ElevatedButton(onPressed: _join, child: const Text('JOIN THE SEASON'))
          else
            const Text("You're in. Every active day counts.", style: TextStyle(color: OsirisTheme.success)),
          if (clubs.isNotEmpty) ...[
            const SizedBox(height: 16),
            const Text('CLUB STANDINGS', style: TextStyle(letterSpacing: 1.2, fontSize: 12, color: Colors.white70)),
            for (final c in clubs)
              ListTile(
                dense: true,
                leading: Text('#${c['rank']}'),
                title: Text(c['name'] as String, style: TextStyle(
                    fontWeight: (c['is_mine'] as bool? ?? false) ? FontWeight.bold : FontWeight.normal)),
                trailing: Text('${c['average_points']} avg pts'),
              ),
          ],
          if (players != null) ...[const SizedBox(height: 12), LeaderboardView(board: players, compact: true)],
        ]),
      ),
    );
  }
}

/// Shared leaderboard list. Other players who have not opted in show as "Private runner".
class LeaderboardView extends StatelessWidget {
  final Leaderboard board;
  final bool compact;

  const LeaderboardView({super.key, required this.board, this.compact = false});

  @override
  Widget build(BuildContext context) {
    final rows = compact ? board.rows.take(10).toList() : board.rows;
    final meShown = rows.any((r) => r.isMe);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (!compact) Text(board.title.toUpperCase(),
          style: const TextStyle(letterSpacing: 1.2, fontSize: 12, color: Colors.white70)),
      if (rows.isEmpty)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 12),
          child: Text('Nobody has scored yet this week. A short walk puts you on the board.'),
        ),
      for (final r in rows) _row(r),
      if (!meShown && board.myRow != null) ...[const Divider(), _row(board.myRow!)],
      const SizedBox(height: 8),
      Text(board.scoring, style: const TextStyle(color: Colors.white54, fontSize: 12)),
    ]);
  }

  Widget _row(LeaderboardRow r) => ListTile(
        dense: true,
        contentPadding: EdgeInsets.zero,
        leading: SizedBox(width: 36, child: Text('#${r.rank}', style: const TextStyle(fontWeight: FontWeight.bold))),
        title: Text(r.isMe ? '${r.name} (you)' : r.name,
            style: TextStyle(color: r.isMe ? OsirisTheme.secondary : null)),
        subtitle: Text('${r.activeDays} active days  •  ${r.distanceKm.toStringAsFixed(1)} km'),
        trailing: Text('${r.points} pts'),
      );
}
