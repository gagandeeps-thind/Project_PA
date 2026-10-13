import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../api/api_error.dart';
import '../api/challenge_models.dart';
import '../api/growth_models.dart';
import '../providers.dart';
import '../services/location_service.dart';
import '../services/share_helper.dart';
import '../theme.dart';

/// Run screen: live route recording, challenge course overlay, and nearby challenge
/// markers. Pass a challenge id as the route argument to run that challenge's course.
class MapScreen extends ConsumerStatefulWidget {
  const MapScreen({super.key});

  @override
  ConsumerState<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends ConsumerState<MapScreen> {
  final MapController _mapCtrl = MapController();

  LatLng? _currentPos;
  Position? _lastRunPosition;
  StreamSubscription<Position>? _locationSub;
  Timer? _clock;
  bool _loadingLocation = true;
  bool _busy = false;
  bool _offline = false;

  final List<LatLng> _tracePath = [];
  int? _challengeId;
  CourseRoute? _course;
  List<ChallengeSummary> _nearby = [];

  bool get _isTracing => ref.read(runQueueProvider).active != null;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _init());
  }

  @override
  void dispose() {
    _locationSub?.cancel();
    _clock?.cancel();
    super.dispose();
  }

  Future<void> _init() async {
    final arg = ModalRoute.of(context)?.settings.arguments;
    final active = ref.read(runQueueProvider).active;
    _challengeId = active?.challengeId ?? (arg is int ? arg : null);
    if (_challengeId != null) unawaited(_loadCourse());
    if (active != null) {
      _startClock();
      if (active.isStale) {
        unawaited(_promptStaleRun());
      } else {
        _snack('Recovered your unfinished run. Keep going or tap FINISH.', OsirisTheme.secondary);
      }
    }
    await _initLocation();
  }

  /// A run left open for many hours was almost certainly abandoned; ask instead of resuming.
  Future<void> _promptStaleRun() async {
    final finish = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: OsirisTheme.surface,
        title: const Text('Unfinished run found'),
        content: const Text('A run you started a while ago was never finished. '
            'Submit what was recorded, or discard it and start fresh?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('DISCARD')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('SUBMIT IT')),
        ],
      ),
    );
    if (finish == true) {
      await _finishRun();
    } else {
      await _discard();
    }
  }

  Future<void> _confirmDiscard() async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: OsirisTheme.surface,
        title: const Text('Discard this run?'),
        content: const Text('The recorded route is deleted from this phone and the run will not count.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('KEEP RUNNING')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('DISCARD')),
        ],
      ),
    );
    if (yes == true) await _discard();
  }

  Future<void> _discard() async {
    await ref.read(runQueueProvider).clear();
    _clock?.cancel();
    if (!mounted) return;
    _listen(recording: false);
    setState(() => _tracePath.clear());
    _snack('Run discarded.', OsirisTheme.secondary);
  }

  Future<void> _loadCourse() async {
    try {
      final data = await ref.read(apiClientProvider).getChallengeCourse(_challengeId!);
      if (!mounted) return;
      setState(() => _course = CourseRoute.fromJson(data));
    } catch (e) {
      _snack(ApiError.getMessage(e), OsirisTheme.error);
    }
  }

  Future<void> _initLocation() async {
    try {
      final pos = await LocationService.getCurrentLocation();
      if (!mounted) return;
      // The map is not in the tree until loading ends, so it takes this fix as its
      // initialCenter; calling MapController.move here would throw.
      setState(() {
        _currentPos = LatLng(pos.latitude, pos.longitude);
        _loadingLocation = false;
      });
      unawaited(_fetchNearby());
      _listen(recording: _isTracing);
    } catch (e) {
      if (!mounted) return;
      setState(() => _loadingLocation = false);
      _snack(ApiError.getMessage(e), OsirisTheme.error);
    }
  }

  /// (Re)subscribe to GPS. Recording mode keeps tracking alive with the screen off or the
  /// app in the background (foreground service on Android); browsing mode does not, so no
  /// notification shows while the player is only looking at the map.
  void _listen({required bool recording}) {
    _locationSub?.cancel();
    _locationSub = LocationService.getLocationStream(recording: recording).listen((pos) {
      if (!mounted) return;
      final newPos = LatLng(pos.latitude, pos.longitude);
      setState(() => _currentPos = newPos);
      if (_isTracing) {
        setState(() => _tracePath.add(newPos));
        unawaited(_capturePoint(pos));
      }
    });
  }

  Future<void> _fetchNearby() async {
    final pos = _currentPos;
    if (pos == null) return;
    try {
      final data = await ref.read(apiClientProvider).getNearbyChallenges(pos.latitude, pos.longitude, 5.0);
      if (!mounted) return;
      setState(() {
        _nearby = data.map((c) => ChallengeSummary.fromJson(c as Map<String, dynamic>)).toList();
      });
    } catch (_) {
      // Discovery is supplementary on this screen.
    }
  }

  void _startClock() {
    _clock?.cancel();
    _clock = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  // ── Recording ───────────────────────────────────────────────────────────

  Future<void> _toggleRun() async {
    if (_busy) return;
    if (_isTracing) {
      await _finishRun();
    } else {
      await _startRun();
    }
  }

  Future<void> _startRun() async {
    if (_currentPos == null) return;
    setState(() => _busy = true);
    final api = ref.read(apiClientProvider);
    final now = DateTime.now().toUtc();
    try {
      final created = await api.createRun(activityType: 'run', deviceStartedAt: now.toIso8601String());
      final runId = created['id'] as int;
      await api.startRun(runId, now.toIso8601String());
      await ref.read(runQueueProvider).begin(runId, now,
          userId: ref.read(authProvider)!.id, challengeId: _challengeId);
      _tracePath
        ..clear()
        ..add(_currentPos!);
      _lastRunPosition = null;
      _listen(recording: true);
      _startClock();
    } catch (e) {
      _snack(ApiError.getMessage(e), OsirisTheme.error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _capturePoint(Position position) async {
    final queue = ref.read(runQueueProvider);
    final run = queue.active;
    if (run == null) return;
    double segment = 0;
    if (_lastRunPosition != null) {
      segment = LocationService.distanceBetween(
        _lastRunPosition!.latitude, _lastRunPosition!.longitude,
        position.latitude, position.longitude,
      );
    }
    _lastRunPosition = position;
    await queue.add({
      't_ms': DateTime.now().toUtc().difference(run.startedAt).inMilliseconds,
      'lat': position.latitude,
      'lng': position.longitude,
      'accuracy_m': position.accuracy,
      'speed_mps': position.speed < 0 ? null : position.speed,
      'altitude_m': position.altitude,
    }, segment);
    if (run.pending.length >= 5) await _flush();
  }

  Future<bool> _flush() async {
    try {
      final done = await ref.read(runQueueProvider).flush(ref.read(apiClientProvider));
      if (mounted) setState(() => _offline = !done);
      return done;
    } catch (e) {
      _snack(ApiError.getMessage(e), OsirisTheme.error);
      return false;
    }
  }

  Future<void> _finishRun() async {
    final queue = ref.read(runQueueProvider);
    final run = queue.active;
    if (run == null) return;
    setState(() => _busy = true);
    try {
      if (!await _flush()) {
        _snack('Points are saved on this phone. Tap FINISH again once you are back online.',
            OsirisTheme.secondary);
        return;
      }
      final result = await ref.read(apiClientProvider).finishRun(
            run.runId,
            DateTime.now().toUtc().toIso8601String(),
            'run-${run.runId}-finish',
          );
      await queue.clear();
      _clock?.cancel();
      _listen(recording: false);
      ref.invalidate(progressionProvider);
      if (!mounted) return;
      setState(() {});
      if (result['verification_status'] != 'accepted') {
        final reasons = (result['rejection_reason'] as String? ?? '')
            .split(',')
            .where((r) => r.isNotEmpty)
            .map(explainReason)
            .join('\n');
        await _info('Run not verified', reasons.isEmpty ? 'The run did not pass verification.' : reasons);
        return;
      }
      if (run.challengeId != null) {
        await _submitToChallenge(run.challengeId!, run.runId);
      } else {
        await _celebrate(run.runId, result);
        if (mounted) await _offerCourse(run.runId, result);
      }
    } catch (e) {
      _snack(ApiError.getMessage(e), OsirisTheme.error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _submitToChallenge(int challengeId, int runId) async {
    try {
      final data = await ref.read(apiClientProvider).submitAttempt(challengeId, runId);
      final attempt = AttemptSummary.fromJson(data);
      ref.invalidate(progressionProvider);
      final lines = <String>[
        if (attempt.elapsedSeconds != null && attempt.elapsedSeconds! > 0)
          'Your time: ${formatDuration(attempt.elapsedSeconds!)}  •  Target: ${formatDuration(attempt.targetSeconds)}',
        if (attempt.xpAwarded > 0) '+${attempt.xpAwarded} XP',
        ...attempt.reasonCodes.map(explainReason),
      ];
      final title = switch (attempt.outcome) {
        'won' => 'Challenge won!',
        'lost' => 'Challenge completed',
        _ => attempt.status == 'review_required' ? 'Result in review' : 'Run not counted',
      };
      await _info(title, lines.join('\n'));
    } catch (e) {
      _snack(ApiError.getMessage(e), OsirisTheme.error);
    }
  }

  /// Clear, immediate payoff after a verified run: distance, XP, quest status, what comes
  /// tomorrow, and a one-tap share.
  Future<void> _celebrate(int runId, Map<String, dynamic> result) async {
    TodayData? today;
    try {
      today = TodayData.fromJson(await ref.read(apiClientProvider).getToday());
    } catch (_) {}
    ref.invalidate(todayProvider);
    if (!mounted) return;
    final questDone = today?.today.completed ?? false;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: OsirisTheme.surface,
        title: Row(children: [
          const Icon(Icons.celebration, color: OsirisTheme.conColor),
          const SizedBox(width: 8),
          Text(questDone ? 'Quest complete!' : 'Run verified'),
        ]),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('${formatDistance((result['distance_m'] as num).toDouble())} in '
              '${formatDuration((result['duration_seconds'] as num).toDouble())}',
              style: Theme.of(ctx).textTheme.titleLarge),
          const SizedBox(height: 4),
          Text('+${result['xp_awarded']} XP', style: const TextStyle(color: OsirisTheme.secondary)),
          if (today != null) ...[
            const SizedBox(height: 12),
            Text('This week: ${today.week.activeDays} of ${today.week.activeDaysTarget} active days'),
            const SizedBox(height: 4),
            Text('Tomorrow: ${today.tomorrow.title}', style: const TextStyle(color: Colors.white70)),
          ],
        ]),
        actions: [
          TextButton.icon(
            onPressed: () => ShareHelper.shareAchievement(ctx, ref, 'run', runId),
            icon: const Icon(Icons.ios_share),
            label: const Text('SHARE'),
          ),
          ElevatedButton(onPressed: () => Navigator.pop(ctx), child: const Text('NICE')),
        ],
      ),
    );
  }

  Future<void> _offerCourse(int runId, Map<String, dynamic> result) async {
    final ctrl = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: OsirisTheme.surface,
        title: const Text('Make it a challenge?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Register this route as a course others can challenge? '
                'The first and last 150 m are trimmed off for your privacy.'),
            const SizedBox(height: 12),
            TextField(
              controller: ctrl,
              maxLength: 60,
              decoration: const InputDecoration(labelText: 'Course name'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('NOT NOW')),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, ctrl.text.trim()),
            child: const Text('REGISTER'),
          ),
        ],
      ),
    );
    if (name == null) return;
    if (name.length < 3) {
      _snack('Course names need at least 3 characters.', OsirisTheme.error);
      return;
    }
    try {
      await ref.read(apiClientProvider).registerCourse(runId, name);
      ref.invalidate(progressionProvider);
      _snack('Course registered. Publish a challenge from My Courses.', OsirisTheme.success);
    } catch (e) {
      _snack(ApiError.getMessage(e), OsirisTheme.error);
    }
  }

  // ── UI helpers ──────────────────────────────────────────────────────────

  void _snack(String message, Color color) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message), backgroundColor: color));
  }

  Future<void> _info(String title, String body) {
    return showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: OsirisTheme.surface,
        title: Text(title),
        content: Text(body),
        actions: [ElevatedButton(onPressed: () => Navigator.pop(ctx), child: const Text('OK'))],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final run = ref.watch(runQueueProvider).active;
    final course = _course;
    final elapsed = run == null ? Duration.zero : DateTime.now().toUtc().difference(run.startedAt);
    final paceSecPerKm = run != null && run.distanceM > 50 ? elapsed.inSeconds / (run.distanceM / 1000) : null;

    return Scaffold(
      appBar: AppBar(
        title: Text(_challengeId == null ? 'RUN' : 'CHALLENGE RUN'),
        actions: [
          if (run != null)
            IconButton(
              tooltip: 'Discard run',
              icon: const Icon(Icons.delete_outline),
              onPressed: _busy ? null : _confirmDiscard,
            ),
        ],
      ),
      body: _loadingLocation
          ? const Center(child: CircularProgressIndicator())
          : Stack(
              children: [
                FlutterMap(
                  mapController: _mapCtrl,
                  options: MapOptions(
                    initialCenter: _currentPos ?? const LatLng(0, 0),
                    initialZoom: 16,
                  ),
                  children: [
                    TileLayer(
                      urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                      userAgentPackageName: 'com.osiris.osiris_customer',
                    ),
                    if (course != null && course.route.length >= 2) ...[
                      PolylineLayer(polylines: [
                        Polyline(points: course.route, color: OsirisTheme.secondary.withAlpha(180), strokeWidth: 6),
                      ]),
                      CircleLayer(circles: [
                        CircleMarker(
                          point: course.route.first,
                          radius: course.startRadiusM,
                          useRadiusInMeter: true,
                          color: OsirisTheme.success.withAlpha(60),
                          borderColor: OsirisTheme.success,
                          borderStrokeWidth: 2,
                        ),
                        CircleMarker(
                          point: course.route.last,
                          radius: course.startRadiusM,
                          useRadiusInMeter: true,
                          color: OsirisTheme.error.withAlpha(50),
                          borderColor: OsirisTheme.error,
                          borderStrokeWidth: 2,
                        ),
                      ]),
                    ],
                    if (_tracePath.length >= 2)
                      PolylineLayer(polylines: [
                        Polyline(points: _tracePath, color: OsirisTheme.primary, strokeWidth: 4),
                      ]),
                    if (_challengeId == null && _nearby.isNotEmpty)
                      MarkerLayer(
                        markers: _nearby
                            .map((c) => Marker(
                                  point: c.marker,
                                  width: 44,
                                  height: 44,
                                  child: GestureDetector(
                                    onTap: run == null
                                        ? () => Navigator.of(context).pushNamed('/challenge', arguments: c.id)
                                        : null,
                                    child: Tooltip(
                                      message: '${c.title} • ${formatDistance(c.courseDistanceM)}',
                                      child: const Icon(Icons.emoji_events, color: Colors.amber, size: 36),
                                    ),
                                  ),
                                ))
                            .toList(),
                      ),
                    if (_currentPos != null)
                      MarkerLayer(markers: [
                        Marker(
                          point: _currentPos!,
                          width: 20,
                          height: 20,
                          child: Container(
                            decoration: BoxDecoration(
                              color: OsirisTheme.primary,
                              shape: BoxShape.circle,
                              border: Border.all(color: Colors.white, width: 2),
                            ),
                          ),
                        ),
                      ]),
                    const RichAttributionWidget(attributions: [
                      TextSourceAttribution('OpenStreetMap contributors'),
                    ]),
                  ],
                ),
                if (_challengeId != null && run == null)
                  const Positioned(
                    top: 12,
                    left: 12,
                    right: 12,
                    child: Card(
                      child: Padding(
                        padding: EdgeInsets.all(12),
                        child: Text(
                          'Go to the green start zone, then tap START. Finish inside the red zone. '
                          'Run safely: obey traffic rules and stop if you feel unwell.',
                        ),
                      ),
                    ),
                  ),
                if (run != null)
                  Positioned(
                    top: 12,
                    left: 12,
                    right: 12,
                    child: Card(
                      color: OsirisTheme.surface.withAlpha(235),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceAround,
                          children: [
                            _Metric(label: 'TIME', value: formatDuration(elapsed.inSeconds.toDouble())),
                            _Metric(label: 'DISTANCE', value: formatDistance(run.distanceM)),
                            _Metric(
                              label: 'PACE /km',
                              value: paceSecPerKm == null ? '--' : formatDuration(paceSecPerKm),
                            ),
                            _Metric(
                              label: _offline ? 'OFFLINE' : 'SYNCED',
                              value: '${run.uploaded}/${run.nextSequence}',
                              color: _offline ? Colors.orange : null,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _busy ? null : _toggleRun,
        backgroundColor: run != null ? OsirisTheme.error : OsirisTheme.primary,
        icon: _busy
            ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
            : Icon(run != null ? Icons.stop : Icons.play_arrow),
        label: Text(run != null ? 'FINISH RUN' : 'START RUN'),
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;

  const _Metric({required this.label, required this.value, this.color});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(value, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: color)),
        const SizedBox(height: 2),
        Text(label, style: TextStyle(fontSize: 11, color: color ?? Colors.white60)),
      ],
    );
  }
}
