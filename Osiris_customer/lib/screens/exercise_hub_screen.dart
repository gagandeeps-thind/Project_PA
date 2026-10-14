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

/// Pick a camera-verified bodyweight exercise, see personal bests and recent sets.
class ExerciseHubScreen extends ConsumerWidget {
  const ExerciseHubScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final catalog = ref.watch(exerciseCatalogProvider);
    final history = ref.watch(exerciseHistoryProvider);
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
              const Card(
                child: ListTile(
                  leading: Icon(Icons.lock_outline, color: OsirisTheme.secondary),
                  title: Text('Your camera stays on your phone'),
                  subtitle: Text('Reps are counted on this device. No video or photos are saved or uploaded; '
                      'only your rep count and timings are.'),
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
                    onTap: () => Navigator.of(context)
                        .push(MaterialPageRoute(builder: (_) => ExerciseCameraScreen(spec: spec)))
                        .then((_) => ref.invalidate(exerciseHistoryProvider)),
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
