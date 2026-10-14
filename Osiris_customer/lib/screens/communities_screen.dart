import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../api/challenge_models.dart';
import '../api/growth_models.dart';
import '../providers.dart';
import '../theme.dart';
import 'rankings_screen.dart';

Color _brand(String? hex) {
  if (hex == null || hex.length != 7) return OsirisTheme.primary;
  return Color(int.parse('FF${hex.substring(1)}', radix: 16));
}

final _myCommunitiesProvider = FutureProvider.autoDispose<List<Community>>((ref) async {
  final rows = await ref.read(apiClientProvider).getMyCommunities();
  return rows.map((r) => Community.fromJson(r as Map<String, dynamic>)).toList();
});

final _discoverProvider = FutureProvider.autoDispose<List<Community>>((ref) async {
  final profile = await ref.watch(myProfileV2Provider.future);
  final rows = await ref.read(apiClientProvider).getCommunities(city: profile.city);
  return rows.map((r) => Community.fromJson(r as Map<String, dynamic>)).toList();
});

/// Clubs, gyms, university groups, and workplaces: yours first, then ones near you.
class CommunitiesScreen extends ConsumerWidget {
  const CommunitiesScreen({super.key});

  Future<void> _joinWithCode(BuildContext context, WidgetRef ref) async {
    final slugCtrl = TextEditingController();
    final codeCtrl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: OsirisTheme.surface,
        title: const Text('Join a private group'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: slugCtrl, decoration: const InputDecoration(labelText: 'Group ID (from the organiser)')),
          TextField(controller: codeCtrl, decoration: const InputDecoration(labelText: 'Join code')),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('CANCEL')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('JOIN')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref.read(apiClientProvider).joinCommunity(slugCtrl.text.trim(), joinCode: codeCtrl.text.trim());
      ref.invalidate(_myCommunitiesProvider);
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(ApiError.getMessage(e)), backgroundColor: OsirisTheme.error),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final mine = ref.watch(_myCommunitiesProvider);
    final discover = ref.watch(_discoverProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('CLUBS & GROUPS'), actions: [
        IconButton(icon: const Icon(Icons.vpn_key_outlined), tooltip: 'Join with a code',
            onPressed: () => _joinWithCode(context, ref)),
      ]),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(_myCommunitiesProvider);
          ref.invalidate(_discoverProvider);
        },
        child: ListView(padding: const EdgeInsets.all(16), children: [
          const Text('YOUR GROUPS', style: TextStyle(letterSpacing: 1.2, fontSize: 12, color: Colors.white70)),
          const SizedBox(height: 8),
          ...mine.when(
            loading: () => [const LinearProgressIndicator()],
            error: (e, _) => [Text(ApiError.getMessage(e))],
            data: (list) => list.isEmpty
                ? [const Text('Join your running club, gym, or team to compete together.')]
                : list.map((c) => _CommunityTile(community: c)).toList(),
          ),
          const SizedBox(height: 24),
          const Text('NEAR YOU', style: TextStyle(letterSpacing: 1.2, fontSize: 12, color: Colors.white70)),
          const SizedBox(height: 8),
          ...discover.when(
            loading: () => [const LinearProgressIndicator()],
            error: (e, _) => [Text(ApiError.getMessage(e))],
            data: (list) {
              final others = list.where((c) => !c.isMember).toList();
              if (others.isEmpty) {
                return [const Text('No other public groups in your city yet. Set your city in Settings.')];
              }
              return others.map((c) => _CommunityTile(community: c)).toList();
            },
          ),
        ]),
      ),
    );
  }
}

class _CommunityTile extends StatelessWidget {
  final Community community;

  const _CommunityTile({required this.community});

  @override
  Widget build(BuildContext context) {
    final c = community;
    return Card(
      child: ListTile(
        leading: CircleAvatar(backgroundColor: _brand(c.brandColor), child: Text(c.name.characters.first)),
        title: Row(children: [
          Flexible(child: Text(c.name, overflow: TextOverflow.ellipsis)),
          if (c.verified) const Padding(
            padding: EdgeInsets.only(left: 6),
            child: Icon(Icons.verified, size: 16, color: OsirisTheme.secondary),
          ),
        ]),
        subtitle: Text('${communityKindLabels[c.kind] ?? 'Community'}  •  ${c.memberCount} members'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => CommunityDetailScreen(slug: c.slug),
        )),
      ),
    );
  }
}

/// A community's branded page: team goal, featured challenges, and its weekly leaderboard.
class CommunityDetailScreen extends ConsumerStatefulWidget {
  final String slug;

  const CommunityDetailScreen({super.key, required this.slug});

  @override
  ConsumerState<CommunityDetailScreen> createState() => _CommunityDetailScreenState();
}

class _CommunityDetailScreenState extends ConsumerState<CommunityDetailScreen> {
  Community? _community;
  List<ChallengeSummary> _challenges = [];
  Leaderboard? _board;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = ref.read(apiClientProvider);
    try {
      final c = Community.fromJson(await api.getCommunity(widget.slug));
      final challenges = (await api.getCommunityChallenges(widget.slug))
          .map((j) => ChallengeSummary.fromJson(j as Map<String, dynamic>))
          .toList();
      final board = c.isMember ? Leaderboard.fromJson(await api.getCommunityLeaderboard(widget.slug)) : null;
      if (!mounted) return;
      setState(() {
        _community = c;
        _challenges = challenges;
        _board = board;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = ApiError.getMessage(e));
    }
  }

  Future<void> _toggleMembership() async {
    final c = _community!;
    setState(() => _busy = true);
    try {
      if (c.isMember) {
        await ref.read(apiClientProvider).leaveCommunity(c.slug);
      } else {
        await ref.read(apiClientProvider).joinCommunity(c.slug);
      }
      await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(ApiError.getMessage(e)), backgroundColor: OsirisTheme.error),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _report() async {
    try {
      final res = await ref.read(apiClientProvider).report(
            targetType: 'community', targetRef: widget.slug, reason: 'spam');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(res['message'] as String)));
      }
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
    final c = _community;
    return Scaffold(
      appBar: AppBar(
        title: Text(c?.name ?? 'GROUP'),
        backgroundColor: c == null ? null : _brand(c.brandColor).withValues(alpha: 0.6),
        actions: [
          PopupMenuButton<String>(
            onSelected: (_) => _report(),
            itemBuilder: (_) => const [PopupMenuItem(value: 'report', child: Text('Report this group'))],
          ),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : c == null
              ? const Center(child: CircularProgressIndicator())
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(padding: const EdgeInsets.all(16), children: [
                    Row(children: [
                      Text(communityKindLabels[c.kind] ?? 'Community', style: const TextStyle(color: Colors.white70)),
                      if (c.verified) ...const [
                        SizedBox(width: 8),
                        Icon(Icons.verified, size: 16, color: OsirisTheme.secondary),
                        Text(' Verified', style: TextStyle(color: OsirisTheme.secondary)),
                      ],
                    ]),
                    if (c.description != null) ...[const SizedBox(height: 8), Text(c.description!)],
                    if (c.perkText != null)
                      Card(
                        child: ListTile(
                          leading: const Icon(Icons.card_giftcard, color: OsirisTheme.conColor),
                          title: const Text('Member perk'),
                          subtitle: Text(c.perkText!),
                        ),
                      ),
                    if (c.joinCode != null)
                      Card(child: ListTile(
                        leading: const Icon(Icons.vpn_key_outlined),
                        title: Text('Join code: ${c.joinCode}'),
                        subtitle: Text('Group ID: ${c.slug}. Share both with your members.'),
                      )),
                    const SizedBox(height: 12),
                    if (c.myRole != 'owner')
                      ElevatedButton(
                        onPressed: _busy ? null : _toggleMembership,
                        child: Text(c.isMember ? 'LEAVE GROUP' : 'JOIN GROUP'),
                      ),
                    if (c.teamGoal != null) ...[
                      const SizedBox(height: 16),
                      _TeamGoalCard(goal: c.teamGoal!),
                    ],
                    const SizedBox(height: 16),
                    const Text('GROUP CHALLENGES', style: TextStyle(letterSpacing: 1.2, fontSize: 12, color: Colors.white70)),
                    if (_challenges.isEmpty) const Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: Text('No featured challenges right now.'),
                    ),
                    for (final ch in _challenges)
                      Card(child: ListTile(
                        leading: const Icon(Icons.flag_outlined),
                        title: Text(ch.title),
                        subtitle: Text('${formatDistance(ch.courseDistanceM)}  •  target ${formatDuration(ch.targetSeconds)}  •  free'),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () => Navigator.of(context).pushNamed('/challenge', arguments: ch.id),
                      )),
                    if (_board != null) ...[
                      const SizedBox(height: 16),
                      LeaderboardView(board: _board!),
                    ] else if (!c.isMember)
                      const Padding(
                        padding: EdgeInsets.only(top: 16),
                        child: Text('Join to see the weekly leaderboard.', style: TextStyle(color: Colors.white70)),
                      ),
                  ]),
                ),
    );
  }
}

class _TeamGoalCard extends StatelessWidget {
  final TeamGoal goal;

  const _TeamGoalCard({required this.goal});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('TEAM GOAL THIS WEEK', style: TextStyle(letterSpacing: 1.2, fontSize: 12, color: Colors.white70)),
          const SizedBox(height: 8),
          Text('${goal.progressKm.toStringAsFixed(1)} of ${goal.goalKm.toStringAsFixed(0)} km together',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(value: goal.fraction, minHeight: 10),
          ),
          const SizedBox(height: 6),
          Text(goal.completed
              ? 'Goal reached. Nice work, team.'
              : '${goal.activeMembers} members active so far. Every verified km counts (up to 10 km a day each).',
              style: const TextStyle(color: Colors.white70, fontSize: 13)),
        ]),
      ),
    );
  }
}
