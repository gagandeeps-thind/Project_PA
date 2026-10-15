import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osiris_customer/api/models.dart';
import 'package:osiris_customer/exercise/rep_engine.dart';
import 'package:osiris_customer/providers.dart';

/// A signed-in player without secure storage or network.
class _SignedIn extends AuthNotifier {
  @override
  UserProfile? build() => UserProfile.fromJson({'id': 7, 'role': 'player'});
}

const _emptySummary = SessionSummary(
  exerciseKey: 'pushup',
  rulesVersion: 'exercise-rules-v1',
  durationS: 10,
  repsAttempted: 0,
  repsValid: 0,
  holdS: 0,
  formScore: 0,
  verdict: 'rejected',
  reasons: ['no_valid_reps'],
  reps: [],
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('without a local database the exercises still load from the bundled catalog', () async {
    final container = ProviderContainer(overrides: [
      exerciseStoreProvider.overrideWith((ref) async => throw StateError('no sqlite on this platform')),
    ]);
    addTearDown(container.dispose);
    final catalog = await container.read(exerciseCatalogProvider.future);
    expect(catalog.exercises, hasLength(7));
    expect(catalog.rulesVersion, 'exercise-rules-v1');
  });

  test('without a local database a signed-in player sees an empty history, not an error', () async {
    final container = ProviderContainer(overrides: [
      authProvider.overrideWith(_SignedIn.new),
      exerciseStoreProvider.overrideWith((ref) async => throw StateError('disk full')),
    ]);
    addTearDown(container.dispose);
    final history = await container.read(exerciseHistoryProvider.future);
    expect(history.recent, isEmpty);
    expect(history.bests, isEmpty);
  });

  test('a set that cannot be saved is reported as not saved', () async {
    final container = ProviderContainer(overrides: [
      authProvider.overrideWith(_SignedIn.new),
      exerciseStoreProvider.overrideWith((ref) async => throw StateError('corrupt')),
    ]);
    addTearDown(container.dispose);
    final record = container.read(exerciseRecorderProvider);
    await expectLater(record(_emptySummary, DateTime.utc(2026, 10, 15)), throwsStateError);
  });
}
