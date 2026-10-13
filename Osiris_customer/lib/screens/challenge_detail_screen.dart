import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../api/challenge_models.dart';
import '../providers.dart';
import '../services/share_helper.dart';
import '../theme.dart';

/// Challenge terms, join, course preview (after joining), and the player's result.
/// Route argument: the challenge id.
class ChallengeDetailScreen extends ConsumerStatefulWidget {
  const ChallengeDetailScreen({super.key});

  @override
  ConsumerState<ChallengeDetailScreen> createState() => _ChallengeDetailScreenState();
}

class _ChallengeDetailScreenState extends ConsumerState<ChallengeDetailScreen> {
  int? _id;
  ChallengeSummary? _challenge;
  CourseRoute? _course;
  bool _loading = true;
  bool _joining = false;
  String? _error;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_id == null) {
      _id = ModalRoute.of(context)?.settings.arguments as int?;
      _load();
    }
  }

  Future<void> _load() async {
    final id = _id;
    if (id == null) return;
    final api = ref.read(apiClientProvider);
    try {
      final c = ChallengeSummary.fromJson(await api.getChallenge(id));
      CourseRoute? course;
      if (c.isMine || c.myAttempt != null) {
        course = CourseRoute.fromJson(await api.getChallengeCourse(id));
      }
      if (!mounted) return;
      setState(() {
        _challenge = c;
        _course = course;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = ApiError.getMessage(e);
        _loading = false;
      });
    }
  }

  Future<void> _join() async {
    setState(() => _joining = true);
    try {
      await ref.read(apiClientProvider).joinChallenge(_id!);
      await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(ApiError.getMessage(e)), backgroundColor: OsirisTheme.error),
        );
      }
    } finally {
      if (mounted) setState(() => _joining = false);
    }
  }

  Future<void> _safetyAction(String action) async {
    final api = ref.read(apiClientProvider);
    try {
      String message;
      if (action == 'block') {
        await api.blockChallengeCreator(_id!);
        message = "Blocked. You won't see this player's challenges.";
      } else {
        final res = await api.report(targetType: 'challenge', targetId: _id, reason: action);
        message = res['message'] as String;
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
      if (action == 'block') Navigator.of(context).pop();
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
    final c = _challenge;
    return Scaffold(
      appBar: AppBar(title: const Text('CHALLENGE'), actions: [
        if (c != null && c.status == 'open')
          IconButton(
            icon: const Icon(Icons.person_add_alt),
            tooltip: 'Invite a friend',
            onPressed: () => ShareHelper.inviteToChallenge(context, ref, c.id),
          ),
        if (c != null && !c.isMine)
          PopupMenuButton<String>(
            onSelected: _safetyAction,
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'unsafe_route', child: Text('Report unsafe route')),
              PopupMenuItem(value: 'cheating', child: Text('Report cheating')),
              PopupMenuItem(value: 'inappropriate_name', child: Text('Report offensive title')),
              PopupMenuItem(value: 'block', child: Text('Block this player')),
            ],
          ),
      ]),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!, style: const TextStyle(color: OsirisTheme.error)))
              : c == null
                  ? const SizedBox.shrink()
                  : RefreshIndicator(onRefresh: _load, child: _content(c)),
    );
  }

  Widget _content(ChallengeSummary c) {
    final attempt = c.myAttempt;
    final canRun = c.status == 'open' &&
        attempt != null &&
        (attempt.status == 'joined' || attempt.status == 'rejected');
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(c.title, style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 4),
        Text('${c.status.toUpperCase()} • ${c.closesIn}', style: const TextStyle(color: Colors.white60)),
        const SizedBox(height: 16),
        if (_course != null && _course!.route.length >= 2) _preview(_course!),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('TERMS', style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 1.5)),
                const SizedBox(height: 8),
                _row('Course distance', formatDistance(c.courseDistanceM)),
                _row('Time to beat', formatDuration(c.targetSeconds)),
                _row('Closes', '${c.closesAt.toString().substring(0, 16)} (${c.closesIn})'),
                _row('Entry cost', c.entryCrystals == 0 ? 'Free' : '${c.entryCrystals} crystals'),
                _row('Reward', '+${c.winXp} XP for a win, +${c.participationXp} XP for a verified finish'),
                _row('Attempts so far', '${c.attemptCount}'),
                const SizedBox(height: 8),
                const Text(
                  'Privacy: the map shows only an approximate area. The exact route is shared '
                  'with players who join. Results are shown without names.',
                  style: TextStyle(color: Colors.white60, fontSize: 12),
                ),
              ],
            ),
          ),
        ),
        if (c.safetyNotes != null && c.safetyNotes!.isNotEmpty)
          Card(
            color: Colors.orange.withAlpha(30),
            child: ListTile(
              leading: const Icon(Icons.health_and_safety, color: Colors.orange),
              title: const Text('Safety notes'),
              subtitle: Text(c.safetyNotes!),
            ),
          ),
        if (attempt != null) _attemptCard(attempt),
        const SizedBox(height: 16),
        if (c.isMine)
          const Text('This is your challenge. You earn XP each time a challenger fails to beat your time.',
              textAlign: TextAlign.center, style: TextStyle(color: Colors.white60))
        else if (attempt == null && c.status == 'open')
          ElevatedButton.icon(
            onPressed: _joining ? null : _join,
            icon: const Icon(Icons.how_to_reg),
            label: Text(_joining ? 'JOINING…' : 'JOIN CHALLENGE'),
          )
        else if (canRun)
          ElevatedButton.icon(
            onPressed: () async {
              await Navigator.of(context).pushNamed('/map', arguments: c.id);
              _load();
            },
            icon: const Icon(Icons.directions_run),
            label: Text(attempt.status == 'rejected' ? 'TRY AGAIN' : 'RUN THIS COURSE'),
          ),
      ],
    );
  }

  Widget _preview(CourseRoute course) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: SizedBox(
          height: 200,
          child: FlutterMap(
            options: MapOptions(
              initialCameraFit: CameraFit.coordinates(
                coordinates: course.route,
                padding: const EdgeInsets.all(24),
              ),
              interactionOptions: const InteractionOptions(flags: InteractiveFlag.none),
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.osiris.osiris_customer',
              ),
              PolylineLayer(polylines: [
                Polyline(points: course.route, color: OsirisTheme.secondary, strokeWidth: 5),
              ]),
              CircleLayer(circles: [
                CircleMarker(point: course.route.first, radius: 8, color: OsirisTheme.success),
                CircleMarker(point: course.route.last, radius: 8, color: OsirisTheme.error),
              ]),
            ],
          ),
        ),
      ),
    );
  }

  Widget _attemptCard(AttemptSummary a) {
    final color = a.outcome == 'won'
        ? OsirisTheme.success
        : a.status == 'rejected'
            ? OsirisTheme.error
            : OsirisTheme.secondary;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Text('YOUR ATTEMPT', style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 1.5)),
              const Spacer(),
              Text(a.label, style: TextStyle(color: color, fontWeight: FontWeight.bold)),
            ]),
            if (a.elapsedSeconds != null && a.elapsedSeconds! > 0) ...[
              const SizedBox(height: 8),
              _row('Your time', formatDuration(a.elapsedSeconds!)),
            ],
            if (a.courseCoverage != null) _row('On course', '${(a.courseCoverage! * 100).round()}%'),
            if (a.xpAwarded > 0) _row('XP earned', '+${a.xpAwarded}'),
            if (a.status == 'accepted' && (a.outcome == 'won' || a.outcome == 'lost'))
              Align(
                alignment: Alignment.centerRight,
                child: TextButton.icon(
                  onPressed: () => ShareHelper.shareAchievement(context, ref, 'challenge_result', a.id),
                  icon: const Icon(Icons.ios_share, size: 18),
                  label: const Text('SHARE RESULT'),
                ),
              ),
            for (final r in a.reasonCodes)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text('• ${explainReason(r)}', style: const TextStyle(color: Colors.white70)),
              ),
          ],
        ),
      ),
    );
  }

  Widget _row(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 130, child: Text(label, style: const TextStyle(color: Colors.white60))),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
