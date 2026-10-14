import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../api/growth_models.dart';
import '../providers.dart';
import '../services/location_service.dart';
import '../theme.dart';

/// Home screen. Answers "what is my next physical quest?" at a glance: today's quest with
/// a one-tap start, this week's goal and streak, tomorrow's quest, and one nearby
/// challenge.
class TodayScreen extends ConsumerStatefulWidget {
  const TodayScreen({super.key});

  @override
  ConsumerState<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends ConsumerState<TodayScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      ref.read(apiClientProvider).trackEvent('app_opened', installId: ref.read(installIdProvider));
      try {
        final pos = await LocationService.getCurrentLocation();
        ref.read(lastKnownPositionProvider.notifier).set(pos.latitude, pos.longitude);
      } catch (_) {
        // No location: the quest still works; only the nearby challenge is skipped.
      }
    });
  }

  Future<void> _grantConsent() async {
    try {
      await ref.read(apiClientProvider).updateMyProfile({'location_consent': true});
      ref.invalidate(todayProvider);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(ApiError.getMessage(e)), backgroundColor: OsirisTheme.error),
      );
    }
  }

  void _startQuest() {
    ref.read(apiClientProvider).trackEvent('run_started', properties: {'source': 'today'});
    Navigator.of(context).pushNamed('/map').then((_) => ref.invalidate(todayProvider));
  }

  @override
  Widget build(BuildContext context) {
    final today = ref.watch(todayProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('OSIRIS'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            tooltip: 'Settings',
            onPressed: () => Navigator.of(context).pushNamed('/settings'),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(todayProvider),
        child: today.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListView(padding: const EdgeInsets.all(24), children: [
            Text(ApiError.getMessage(e), style: const TextStyle(color: OsirisTheme.error)),
            const SizedBox(height: 12),
            OutlinedButton(onPressed: () => ref.invalidate(todayProvider), child: const Text('TRY AGAIN')),
          ]),
          data: (t) => ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
            children: [
              Text('Hi ${t.displayName}', style: Theme.of(context).textTheme.headlineSmall),
              Text('${t.performanceRank} ${t.identity}  •  ${t.xp} XP',
                  style: const TextStyle(color: Colors.white70)),
              const SizedBox(height: 16),
              if (t.needsLocationConsent) _ConsentBanner(onAllow: _grantConsent),
              _QuestCard(quest: t.today, onStart: _startQuest),
              const SizedBox(height: 12),
              _WeekCard(week: t.week, streakWeeks: t.streakWeeks),
              const SizedBox(height: 12),
              Card(
                child: ListTile(
                  leading: const Icon(Icons.wb_twilight, color: OsirisTheme.secondary),
                  title: const Text('Tomorrow'),
                  subtitle: Text(t.tomorrow.title),
                ),
              ),
              if (t.starterChallenge != null) ...[
                const SizedBox(height: 12),
                _StarterChallengeCard(challenge: t.starterChallenge!),
              ],
              const SizedBox(height: 20),
              _NavGrid(),
              const SizedBox(height: 20),
              Row(children: [
                const Icon(Icons.health_and_safety_outlined, size: 18, color: Colors.white54),
                const SizedBox(width: 8),
                Expanded(child: Text(t.safetyNote, style: const TextStyle(color: Colors.white54, fontSize: 12))),
              ]),
              const SizedBox(height: 8),
              Center(child: Text(t.tagline, style: const TextStyle(color: Colors.white38, fontSize: 12))),
            ],
          ),
        ),
      ),
    );
  }
}

class _ConsentBanner extends StatelessWidget {
  final VoidCallback onAllow;

  const _ConsentBanner({required this.onAllow});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: OsirisTheme.secondary.withValues(alpha: 0.15),
      child: ListTile(
        leading: const Icon(Icons.location_on_outlined),
        title: const Text('Allow location during runs'),
        subtitle: const Text('Needed to verify your distance. Your route is never shown to others.'),
        trailing: TextButton(onPressed: onAllow, child: const Text('ALLOW')),
      ),
    );
  }
}

class _QuestCard extends StatelessWidget {
  final Quest quest;
  final VoidCallback onStart;

  const _QuestCard({required this.quest, required this.onStart});

  @override
  Widget build(BuildContext context) {
    final label = switch (quest.kind) {
      'starter' => 'YOUR FIRST QUEST',
      'recovery' => 'RECOVERY DAY',
      _ => "TODAY'S QUEST",
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: const TextStyle(color: OsirisTheme.secondary, letterSpacing: 1.2, fontSize: 12)),
            const SizedBox(height: 6),
            Text(quest.title, style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 4),
            Text(quest.description, style: const TextStyle(color: Colors.white70)),
            const SizedBox(height: 14),
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: LinearProgressIndicator(value: quest.fraction, minHeight: 10),
            ),
            const SizedBox(height: 6),
            Text('${kmLabel(quest.progressM)} of ${kmLabel(quest.targetM.toDouble())}  •  +${quest.xp} XP',
                style: const TextStyle(color: Colors.white70, fontSize: 13)),
            const SizedBox(height: 14),
            if (quest.completed)
              Row(children: [
                const Icon(Icons.check_circle, color: OsirisTheme.success),
                const SizedBox(width: 8),
                Expanded(child: Text(quest.rewarded ? 'Done. +${quest.xp} XP earned.' : 'Done!')),
                TextButton(onPressed: onStart, child: const Text('GO AGAIN')),
              ])
            else
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: onStart,
                  icon: const Icon(Icons.play_arrow),
                  label: Text(quest.optional ? 'START (OPTIONAL)' : 'START'),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _WeekCard extends StatelessWidget {
  final WeeklyGoal week;
  final int streakWeeks;

  const _WeekCard({required this.week, required this.streakWeeks});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Text('THIS WEEK', style: TextStyle(letterSpacing: 1.2, fontSize: 12, color: Colors.white70)),
              const Spacer(),
              Icon(Icons.local_fire_department,
                  color: streakWeeks > 0 ? OsirisTheme.conColor : Colors.white24, size: 18),
              const SizedBox(width: 4),
              Text(streakWeeks == 1 ? '1 week streak' : '$streakWeeks week streak'),
            ]),
            const SizedBox(height: 12),
            Row(children: [
              for (var i = 0; i < week.activeDaysTarget; i++)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: Icon(
                    i < week.activeDays ? Icons.circle : Icons.circle_outlined,
                    color: i < week.activeDays ? OsirisTheme.secondary : Colors.white38,
                    size: 22,
                  ),
                ),
              const Spacer(),
              Text(kmLabel(week.distanceM), style: const TextStyle(color: Colors.white70)),
            ]),
            const SizedBox(height: 8),
            Text(
              week.completed
                  ? 'Weekly goal met. Enjoy your rest days.'
                  : '${week.activeDays} of ${week.activeDaysTarget} active days. Rest days never break your streak.',
              style: const TextStyle(color: Colors.white70, fontSize: 13),
            ),
          ],
        ),
      ),
    );
  }
}

class _StarterChallengeCard extends StatelessWidget {
  final Map<String, dynamic> challenge;

  const _StarterChallengeCard({required this.challenge});

  @override
  Widget build(BuildContext context) {
    final km = ((challenge['course_distance_m'] as num?)?.toDouble() ?? 0) / 1000;
    final away = (challenge['distance_km'] as num?)?.toDouble();
    return Card(
      child: ListTile(
        leading: const Icon(Icons.flag_outlined, color: OsirisTheme.primary),
        title: Text(challenge['title'] as String? ?? 'Nearby challenge'),
        subtitle: Text('${km.toStringAsFixed(1)} km course${away == null ? '' : '  •  about ${away.toStringAsFixed(1)} km away'}  •  free'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.of(context).pushNamed('/challenge', arguments: challenge['id'] as int),
      ),
    );
  }
}

class _NavGrid extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    const items = [
      (Icons.flag_outlined, 'Challenges', '/challenges'),
      (Icons.groups_outlined, 'Clubs', '/communities'),
      (Icons.leaderboard_outlined, 'Rankings', '/rankings'),
      (Icons.fitness_center, 'Bodyweight', '/exercise'),
      (Icons.route_outlined, 'My courses', '/courses'),
      (Icons.emoji_events_outlined, 'Progress', '/dashboard'),
      (Icons.person_add_alt, 'Invite', '/settings'),
    ];
    return GridView.count(
      crossAxisCount: 3,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 8,
      crossAxisSpacing: 8,
      childAspectRatio: 1.3,
      children: [
        for (final (icon, label, route) in items)
          Card(
            margin: EdgeInsets.zero,
            child: InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: () => Navigator.of(context).pushNamed(route),
              child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                Icon(icon, color: OsirisTheme.secondary),
                const SizedBox(height: 6),
                Text(label, style: const TextStyle(fontSize: 13)),
              ]),
            ),
          ),
      ],
    );
  }
}
