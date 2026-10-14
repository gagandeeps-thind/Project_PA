import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osiris_customer/exercise/exercise_store.dart';
import 'package:osiris_customer/exercise/pose_frame.dart';
import 'package:osiris_customer/exercise/pose_source.dart';
import 'package:osiris_customer/exercise/rep_engine.dart';
import 'package:osiris_customer/providers.dart';
import 'package:osiris_customer/screens/exercise_camera_screen.dart';
import 'package:osiris_customer/screens/exercise_hub_screen.dart';

import 'pose_synth.dart';

/// Scripted pose stream standing in for camera + ML Kit.
class FakePoseSource extends PoseSource {
  final _controller = StreamController<PoseFrame>.broadcast(sync: true);
  bool started = false;
  bool stopped = false;

  @override
  Stream<PoseFrame> get frames => _controller.stream;

  @override
  Size? get imageSize => const Size(480, 640);

  @override
  bool get mirrored => true;

  @override
  Future<void> start() async => started = true;

  @override
  Future<void> stop() async => stopped = true;

  @override
  Widget? buildPreview() => const ColoredBox(color: Colors.black);

  void emitAll(Iterable<PoseFrame> frames) => frames.forEach(_controller.add);
}

/// A camera the player refused, as the camera plugin reports it.
class DeniedPoseSource extends FakePoseSource {
  @override
  Future<void> start() async => throw Exception('CameraAccessDenied: User denied camera access.');
}

void main() {
  final catalog = loadCatalog();

  testWidgets('a push-up set is counted live, verified, saved and reported with XP', (tester) async {
    final source = FakePoseSource();
    SessionSummary? recorded;
    await tester.pumpWidget(ProviderScope(
      overrides: [
        exerciseCatalogProvider.overrideWith((ref) async => catalog),
        poseSourceFactoryProvider.overrideWithValue(() => source),
        exerciseRecorderProvider.overrideWithValue((summary, startedAt) async {
          recorded = summary;
          return SetOutcome(uploaded: true, xpAwarded: summary.repsValid);
        }),
      ],
      child: MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => ExerciseCameraScreen(spec: catalog.byKey('pushup')!))),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(source.started, isTrue);
    expect(find.text('START'), findsOneWidget);
    expect(find.textContaining('Place the phone'), findsOneWidget);

    // Poses before START are previewed but not counted.
    final noise = Noise(21);
    source.emitAll(cycles(humanTempo(2, 1600),
        (p, _) => sideBody(torsoDeg: 190, elbow: swing(p, 170, 80), shoulder: 80, noise: noise)));
    await tester.pump();
    expect(find.byKey(const Key('exercise-count')), findsOneWidget);
    expect(tester.widget<Text>(find.byKey(const Key('exercise-count'))).data, '0');

    await tester.tap(find.text('START'));
    await tester.pump();
    source.emitAll(cycles(humanTempo(12, 1600, seed: 3),
        (p, _) => sideBody(torsoDeg: 190, elbow: swing(p, 170, 80), shoulder: 80, noise: noise), startMs: 10000));
    await tester.pump();
    expect(tester.widget<Text>(find.byKey(const Key('exercise-count'))).data, '12');

    await tester.tap(find.text('FINISH'));
    await tester.pumpAndSettle();
    expect(recorded?.repsValid, 12);
    expect(recorded?.verdict, 'verified');
    expect(find.text('Verified'), findsOneWidget);
    expect(find.text('Push-up: 12 reps'), findsOneWidget);
    expect(find.text('+12 XP'), findsOneWidget);

    await tester.tap(find.text('DONE'));
    await tester.pumpAndSettle();
    expect(find.text('open'), findsOneWidget);
    expect(source.stopped, isTrue, reason: 'the camera is released when the screen closes');
  });

  testWidgets('a set with no real reps is reported as not verified', (tester) async {
    final source = FakePoseSource();
    await tester.pumpWidget(ProviderScope(
      overrides: [
        exerciseCatalogProvider.overrideWith((ref) async => catalog),
        poseSourceFactoryProvider.overrideWithValue(() => source),
        exerciseRecorderProvider.overrideWithValue((s, _) async => const SetOutcome(uploaded: false, xpAwarded: 0)),
      ],
      child: MaterialApp(home: ExerciseCameraScreen(spec: catalog.byKey('pushup')!)),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('START'));
    await tester.pump();
    // Standing arm curls: the elbow moves, but the body is upright.
    final noise = Noise(22);
    source.emitAll(cycles(humanTempo(6, 1600),
        (p, _) => sideBody(torsoDeg: -90, elbow: swing(p, 170, 80), shoulder: 80, noise: noise)));
    await tester.pump();
    expect(tester.widget<Text>(find.byKey(const Key('exercise-count'))).data, '0');
    await tester.tap(find.text('FINISH'));
    await tester.pumpAndSettle();
    expect(find.text('Not verified'), findsOneWidget);
    expect(find.textContaining('Body position did not match'), findsOneWidget);
    expect(find.textContaining('upload when you are online'), findsOneWidget);
  });

  testWidgets('a denied camera offers settings and retries when the player returns', (tester) async {
    final denied = DeniedPoseSource();
    final granted = FakePoseSource();
    var created = 0;
    await tester.pumpWidget(ProviderScope(
      overrides: [
        exerciseCatalogProvider.overrideWith((ref) async => catalog),
        poseSourceFactoryProvider.overrideWithValue(() => created++ == 0 ? denied : granted),
      ],
      child: MaterialApp(home: ExerciseCameraScreen(spec: catalog.byKey('squat')!)),
    ));
    await tester.pumpAndSettle();
    expect(find.textContaining('Camera access is off'), findsOneWidget);
    expect(find.text('OPEN SETTINGS'), findsOneWidget);
    expect(find.text('START'), findsNothing);

    // The permission dialog closing also pauses and resumes the app. That alone must not ask
    // again (seen on the emulator: the prompt came straight back after "Don't allow").
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(granted.started, isFalse);
    expect(find.textContaining('Camera access is off'), findsOneWidget);

    // Coming back from the settings app must try the camera again, not stay on the error.
    final settingsCalls = <String>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('flutter.baseflow.com/geolocator'),
      (call) async {
        settingsCalls.add(call.method);
        return true;
      },
    );
    await tester.tap(find.text('OPEN SETTINGS'));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(settingsCalls, contains('openAppSettings'));
    expect(granted.started, isTrue);
    expect(find.textContaining('Camera access is off'), findsNothing);
    expect(find.text('START'), findsOneWidget);
  });

  testWidgets('the hub lists every exercise with bests and recent set status', (tester) async {
    StoredSession set(String key, {String sync = 'synced', String? status = 'verified', int xp = 0}) => StoredSession(
          id: '$key$sync',
          userId: 1,
          exerciseKey: key,
          rulesVersion: 'exercise-rules-v1',
          startedAt: DateTime.utc(2026, 10, 14, 8),
          durationS: 60,
          repsAttempted: 10,
          repsValid: 10,
          holdS: 0,
          formScore: 1,
          verdict: 'verified',
          reasons: const [],
          repDurationsS: const [],
          syncState: sync,
          serverStatus: status,
          xpAwarded: xp,
        );
    await tester.pumpWidget(ProviderScope(
      overrides: [
        exerciseCatalogProvider.overrideWith((ref) async => catalog),
        exerciseHistoryProvider.overrideWith((ref) async => ExerciseHistory(
              [set('pushup', xp: 10), set('squat', sync: 'pending', status: null), set('lunge', status: 'review')],
              const {'pushup': 25, 'plank': 61},
            )),
      ],
      child: const MaterialApp(home: ExerciseHubScreen()),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Best 25 reps'), findsOneWidget);
    for (final e in catalog.exercises) {
      await tester.scrollUntilVisible(find.byKey(Key('exercise-${e.key}')), 100);
      expect(find.byKey(Key('exercise-${e.key}')), findsOneWidget);
    }
    expect(find.text('Best 61 s'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Under review'), 100);
    expect(find.text('+10 XP'), findsOneWidget);
    expect(find.text('Waiting to upload'), findsOneWidget);
  });
}
