import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../exercise/exercise_catalog.dart';
import '../exercise/exercise_store.dart';
import '../providers.dart';
import '../theme.dart';
import 'exercise_camera_screen.dart';

IconData exerciseIcon(String key) => switch (key) {
      'pushup' => Icons.fitness_center,
      'squat' => Icons.airline_seat_legroom_extra,
      'lunge' => Icons.directions_walk,
      'situp' => Icons.airline_seat_flat_angled,
      'jumping_jack' => Icons.accessibility_new,
      'high_knees' => Icons.directions_run,
      'plank' => Icons.horizontal_rule,
      _ => Icons.sports_gymnastics,
    };

String formatBest(ExerciseSpec spec, double best) =>
    spec.isHold ? '${best.toStringAsFixed(0)} s' : '${best.toStringAsFixed(0)} reps';

/// Asks for explicit consent to count exercises with the camera. Returns true once granted.
Future<bool> askExerciseConsent(BuildContext context, WidgetRef ref) async {
  final allow = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    builder: (ctx) => const _ConsentSheet(),
  );
  if (allow != true) return false;
  try {
    await ref.read(exerciseConsentProvider.notifier).set(true);
    return true;
  } on Object catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(ApiError.getMessage(e)), backgroundColor: OsirisTheme.error),
      );
    }
    return false;
  }
}

class _ConsentSheet extends StatelessWidget {
  const _ConsentSheet();

  @override
  Widget build(BuildContext context) {
    const points = [
      (Icons.phone_android, 'Camera images are analysed on this phone only, to find where your joints are. '
          'They are never saved or uploaded.'),
      (Icons.cloud_upload_outlined, 'Osiris keeps the exercise, your rep count, rep timings and a form score, '
          'to verify sets and award XP. This is health information.'),
      (Icons.toggle_off_outlined, 'You can withdraw at any time in Settings, and delete your exercise history.'),
    ];
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Count reps with your camera?', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          for (final (icon, text) in points)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(icon, color: OsirisTheme.secondary),
                const SizedBox(width: 12),
                Expanded(child: Text(text)),
              ]),
            ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              key: const Key('exercise-consent-allow'),
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('ALLOW'),
            ),
          ),
          SizedBox(
            width: double.infinity,
            child: TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('NOT NOW')),
          ),
        ]),
      ),
    );
  }
}

/// Pick a camera-verified bodyweight exercise, see personal bests and recent sets.
class ExerciseHubScreen extends ConsumerWidget {
  const ExerciseHubScreen({super.key});

  Future<void> _open(BuildContext context, WidgetRef ref, ExerciseSpec spec) async {
    final consented = ref.read(exerciseConsentProvider).value ?? false;
    if (!consented && !await askExerciseConsent(context, ref)) return;
    if (!context.mounted) return;
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => ExerciseCameraScreen(spec: spec)));
    ref.invalidate(exerciseHistoryProvider);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final catalog = ref.watch(exerciseCatalogProvider);
    final history = ref.watch(exerciseHistoryProvider);
    final consented = ref.watch(exerciseConsentProvider).value ?? false;
    final bests = history.value?.bests ?? const <String, double>{};
    return Scaffold(
      appBar: AppBar(title: const Text('Bodyweight')),
      body: catalog.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(ApiError.getMessage(e), style: const TextStyle(color: OsirisTheme.error))),
        data: (c) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(exerciseHistoryProvider),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
            children: [
              Card(
                child: ListTile(
                  leading: const Icon(Icons.lock_outline, color: OsirisTheme.secondary),
                  title: const Text('Your camera stays on your phone'),
                  subtitle: const Text('Reps are counted on this device. No video or photos are saved or uploaded; '
                      'only your rep count and timings are.'),
                  trailing: consented
                      ? null
                      : TextButton(
                          key: const Key('exercise-consent-open'),
                          onPressed: () => askExerciseConsent(context, ref),
                          child: const Text('ALLOW'),
                        ),
                ),
              ),
              const SizedBox(height: 8),
              for (final spec in c.exercises)
                Card(
                  child: ListTile(
                    key: Key('exercise-${spec.key}'),
                    leading: Icon(exerciseIcon(spec.key), color: OsirisTheme.secondary),
                    title: Text(spec.name),
                    subtitle: Text(spec.camera == 'front' ? 'Face the camera' : 'Side-on to the camera'),
                    trailing: bests[spec.key] == null
                        ? const Icon(Icons.chevron_right)
                        : Text('Best ${formatBest(spec, bests[spec.key]!)}',
                            style: const TextStyle(color: OsirisTheme.secondary)),
                    onTap: () => _open(context, ref, spec),
                  ),
                ),
              const SizedBox(height: 16),
              if (history.value?.recent.isNotEmpty ?? false) ...[
                Text('Recent sets', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                for (final s in history.value!.recent) _RecentSet(session: s, spec: c.byKey(s.exerciseKey)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _RecentSet extends StatelessWidget {
  final StoredSession session;
  final ExerciseSpec? spec;

  const _RecentSet({required this.session, required this.spec});

  @override
  Widget build(BuildContext context) {
    final status = session.syncState == 'pending'
        ? ('Waiting to upload', Colors.white54)
        : session.syncState == 'failed'
            ? ('Not accepted', OsirisTheme.error)
            : switch (session.serverStatus) {
                'verified' => ('+${session.xpAwarded} XP', OsirisTheme.success),
                'review' => ('Under review', Colors.amber),
                _ => ('Not verified', OsirisTheme.error),
              };
    final amount = session.holdS > 0 ? '${session.holdS.toStringAsFixed(0)} s' : '${session.repsValid} reps';
    final d = session.startedAt.toLocal();
    return ListTile(
      dense: true,
      leading: Icon(exerciseIcon(session.exerciseKey), size: 20),
      title: Text('${spec?.name ?? session.exerciseKey} · $amount'),
      subtitle: Text('${d.year}-${_two(d.month)}-${_two(d.day)} ${_two(d.hour)}:${_two(d.minute)}'),
      trailing: Text(status.$1, style: TextStyle(color: status.$2)),
    );
  }

  static String _two(int v) => v.toString().padLeft(2, '0');
}

/// Camera exercise counting consent. Withdrawing asks whether to keep or delete the sets.
class ExerciseConsentTile extends ConsumerWidget {
  const ExerciseConsentTile({super.key});

  Future<void> _withdraw(BuildContext context, WidgetRef ref) async {
    final choice = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Stop counting exercises?'),
        content: const Text('Osiris will stop uploading exercise sets. You can also delete your exercise history '
            'from Osiris and this phone. XP you already earned stays.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('CANCEL')),
          TextButton(onPressed: () => Navigator.pop(ctx, 'keep'), child: const Text('KEEP MY SETS')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, 'delete'),
            child: const Text('DELETE MY SETS', style: TextStyle(color: OsirisTheme.error)),
          ),
        ],
      ),
    );
    if (choice == null) return;
    try {
      await ref.read(exerciseConsentProvider.notifier).set(false, deleteData: choice == 'delete');
    } on Object catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(ApiError.getMessage(e)), backgroundColor: OsirisTheme.error),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final granted = ref.watch(exerciseConsentProvider).value ?? false;
    return SwitchListTile(
      key: const Key('exercise-consent-switch'),
      value: granted,
      onChanged: (v) => v ? askExerciseConsent(context, ref) : _withdraw(context, ref),
      title: const Text('Camera exercise counting'),
      subtitle: const Text('Counts reps on this phone; keeps rep counts and timings'),
    );
  }
}
