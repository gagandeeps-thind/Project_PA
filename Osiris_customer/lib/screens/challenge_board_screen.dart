import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../api/challenge_models.dart';
import '../providers.dart';
import '../services/location_service.dart';
import '../theme.dart';

/// Nearby open challenges, as generalized markers only (no owner, no exact route).
class ChallengeBoardScreen extends ConsumerStatefulWidget {
  const ChallengeBoardScreen({super.key});

  @override
  ConsumerState<ChallengeBoardScreen> createState() => _ChallengeBoardScreenState();
}

class _ChallengeBoardScreenState extends ConsumerState<ChallengeBoardScreen> {
  static const _radii = [2.0, 5.0, 10.0, 25.0];
  double _radiusKm = 5.0;
  List<ChallengeSummary> _challenges = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final pos = await LocationService.getCurrentLocation();
      final data = await ref.read(apiClientProvider).getNearbyChallenges(pos.latitude, pos.longitude, _radiusKm);
      if (!mounted) return;
      setState(() {
        _challenges = data.map((c) => ChallengeSummary.fromJson(c as Map<String, dynamic>)).toList();
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = ApiError.getMessage(e);
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('CHALLENGES'),
        actions: [
          PopupMenuButton<double>(
            tooltip: 'Search radius',
            icon: const Icon(Icons.radar),
            initialValue: _radiusKm,
            onSelected: (r) {
              setState(() => _radiusKm = r);
              _load();
            },
            itemBuilder: (_) => _radii
                .map((r) => PopupMenuItem(value: r, child: Text('Within ${r.round()} km')))
                .toList(),
          ),
        ],
      ),
      body: RefreshIndicator(onRefresh: _load, child: _body()),
    );
  }

  Widget _body() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return ListView(children: [
        Padding(
          padding: const EdgeInsets.all(24),
          child: Text(_error!, textAlign: TextAlign.center, style: const TextStyle(color: OsirisTheme.error)),
        ),
      ]);
    }
    if (_challenges.isEmpty) {
      return ListView(children: [
        Padding(
          padding: const EdgeInsets.all(32),
          child: Column(children: [
            const Icon(Icons.emoji_events_outlined, size: 56, color: Colors.white38),
            const SizedBox(height: 12),
            Text('No open challenges within ${_radiusKm.round()} km.', textAlign: TextAlign.center),
            const SizedBox(height: 8),
            const Text(
              'Record a run, register it as a course, and publish the first one.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white60),
            ),
          ]),
        ),
      ]);
    }
    return ListView.separated(
      padding: const EdgeInsets.all(12),
      itemCount: _challenges.length,
      separatorBuilder: (_, _) => const SizedBox(height: 8),
      itemBuilder: (_, i) => _ChallengeTile(
        challenge: _challenges[i],
        onTap: () async {
          await Navigator.of(context).pushNamed('/challenge', arguments: _challenges[i].id);
          _load();
        },
      ),
    );
  }
}

class _ChallengeTile extends StatelessWidget {
  final ChallengeSummary challenge;
  final VoidCallback onTap;

  const _ChallengeTile({required this.challenge, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = challenge;
    return Card(
      child: ListTile(
        onTap: onTap,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        leading: const Icon(Icons.emoji_events, color: Colors.amber, size: 32),
        title: Text(c.title, style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Text(
            '${formatDistance(c.courseDistanceM)} • beat ${formatDuration(c.targetSeconds)}\n'
            '${c.distanceKm == null ? '' : '~${c.distanceKm} km away • '}${c.closesIn} • ${c.attemptCount} attempts',
          ),
        ),
        isThreeLine: true,
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text('+${c.winXp} XP', style: const TextStyle(color: OsirisTheme.primary, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            if (c.isMine)
              const _Chip(label: 'Yours', color: OsirisTheme.secondary)
            else if (c.myAttempt != null)
              _Chip(label: c.myAttempt!.label, color: OsirisTheme.success),
          ],
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  final String label;
  final Color color;

  const _Chip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        border: Border.all(color: color),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(label, style: TextStyle(color: color, fontSize: 11)),
    );
  }
}
