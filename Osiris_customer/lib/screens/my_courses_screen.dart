import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../api/challenge_models.dart';
import '../providers.dart';
import '../theme.dart';

/// The player's registered courses, with publishing of a challenge on each.
class MyCoursesScreen extends ConsumerStatefulWidget {
  const MyCoursesScreen({super.key});

  @override
  ConsumerState<MyCoursesScreen> createState() => _MyCoursesScreenState();
}

class _MyCoursesScreenState extends ConsumerState<MyCoursesScreen> {
  List<CourseSummary> _courses = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await ref.read(apiClientProvider).getMyCourses();
      if (!mounted) return;
      setState(() {
        _courses = data.map((c) => CourseSummary.fromJson(c as Map<String, dynamic>)).toList();
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

  Future<void> _publish(CourseSummary course) async {
    final input = await showDialog<_PublishInput>(
      context: context,
      builder: (_) => _PublishDialog(course: course),
    );
    if (input == null) return;
    try {
      final data = await ref.read(apiClientProvider).publishChallenge(
            courseId: course.id,
            title: input.title,
            windowHours: input.windowHours,
            safetyNotes: input.safetyNotes,
            idempotencyKey: input.idempotencyKey,
          );
      ref.invalidate(progressionProvider);
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Challenge published.'), backgroundColor: OsirisTheme.success),
      );
      Navigator.of(context).pushNamed('/challenge', arguments: data['id'] as int);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(ApiError.getMessage(e)), backgroundColor: OsirisTheme.error),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('MY COURSES')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: _error != null
                  ? ListView(children: [
                      Padding(
                        padding: const EdgeInsets.all(24),
                        child: Text(_error!, style: const TextStyle(color: OsirisTheme.error)),
                      ),
                    ])
                  : _courses.isEmpty
                      ? ListView(children: const [
                          Padding(
                            padding: EdgeInsets.all(32),
                            child: Text(
                              'No courses yet. Finish a verified run of at least ~0.7 km and '
                              'register it as a course.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Colors.white60),
                            ),
                          ),
                        ])
                      : ListView.separated(
                          padding: const EdgeInsets.all(12),
                          itemCount: _courses.length,
                          separatorBuilder: (_, _) => const SizedBox(height: 8),
                          itemBuilder: (_, i) => _courseTile(_courses[i]),
                        ),
            ),
    );
  }

  Widget _courseTile(CourseSummary c) {
    final Widget action;
    if (c.status != 'active') {
      action = Text(c.status.toUpperCase(), style: const TextStyle(color: OsirisTheme.error));
    } else if (c.openChallengeId != null) {
      action = TextButton(
        onPressed: () => Navigator.of(context).pushNamed('/challenge', arguments: c.openChallengeId),
        child: const Text('VIEW LIVE'),
      );
    } else {
      action = ElevatedButton(onPressed: () => _publish(c), child: const Text('PUBLISH'));
    }
    return Card(
      child: ListTile(
        leading: Icon(c.isLoop ? Icons.loop : Icons.route, color: OsirisTheme.secondary),
        title: Text(c.name, style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text('${formatDistance(c.distanceM)} • your time ${formatDuration(c.benchmarkSeconds)}'),
        trailing: action,
      ),
    );
  }
}

class _PublishInput {
  final String title;
  final int windowHours;
  final String? safetyNotes;
  final String idempotencyKey;

  const _PublishInput(this.title, this.windowHours, this.safetyNotes, this.idempotencyKey);
}

class _PublishDialog extends StatefulWidget {
  final CourseSummary course;

  const _PublishDialog({required this.course});

  @override
  State<_PublishDialog> createState() => _PublishDialogState();
}

class _PublishDialogState extends State<_PublishDialog> {
  static const _windows = {24: '1 day', 72: '3 days', 168: '1 week', 336: '2 weeks'};
  late final TextEditingController _title = TextEditingController(text: 'Beat my ${widget.course.name}');
  final TextEditingController _safety = TextEditingController();
  int _window = 72;
  // One key per dialog, so a retried tap never publishes twice.
  final String _key = 'pub-${DateTime.now().microsecondsSinceEpoch}-${Random().nextInt(1 << 30)}';

  @override
  void dispose() {
    _title.dispose();
    _safety.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: OsirisTheme.surface,
      title: const Text('Publish challenge'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Challengers must beat your time of ${formatDuration(widget.course.benchmarkSeconds)} '
                'over ${formatDistance(widget.course.distanceM)}. Terms cannot be edited after publishing.'),
            const SizedBox(height: 12),
            TextField(controller: _title, maxLength: 80, decoration: const InputDecoration(labelText: 'Title')),
            DropdownButtonFormField<int>(
              initialValue: _window,
              decoration: const InputDecoration(labelText: 'Open for'),
              items: _windows.entries
                  .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                  .toList(),
              onChanged: (v) => setState(() => _window = v ?? _window),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _safety,
              maxLength: 500,
              maxLines: 3,
              decoration: const InputDecoration(
                labelText: 'Safety notes (optional)',
                hintText: 'e.g. busy crossing at the halfway point',
              ),
            ),
            const Text('Entry is free. Rewards are XP and badges.',
                style: TextStyle(color: Colors.white60, fontSize: 12)),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('CANCEL')),
        ElevatedButton(
          onPressed: () {
            final title = _title.text.trim();
            if (title.length < 3) return;
            Navigator.pop(context, _PublishInput(title, _window, _safety.text.trim(), _key));
          },
          child: const Text('PUBLISH'),
        ),
      ],
    );
  }
}
