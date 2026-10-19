import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../api/growth_models.dart';
import '../providers.dart';
import 'exercise_hub_screen.dart' show ExerciseConsentTile;
import '../services/share_helper.dart';
import '../theme.dart';

final _referralProvider = FutureProvider.autoDispose<ReferralSummary>((ref) async {
  return ReferralSummary.fromJson(await ref.read(apiClientProvider).getReferrals());
});

/// Profile, privacy, invites, safety, and account controls in one place.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  Future<void> _update(BuildContext context, WidgetRef ref, Map<String, dynamic> changes) async {
    try {
      await ref.read(apiClientProvider).updateMyProfile(changes);
      ref.invalidate(myProfileV2Provider);
      ref.invalidate(todayProvider);
    } catch (e) {
      if (context.mounted) _error(context, e);
    }
  }

  void _error(BuildContext context, Object e) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(ApiError.getMessage(e)), backgroundColor: OsirisTheme.error),
    );
  }

  Future<String?> _ask(BuildContext context, String title, String label, {String initial = '', bool secret = false}) {
    final ctrl = TextEditingController(text: initial);
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: OsirisTheme.surface,
        title: Text(title),
        content: TextField(controller: ctrl, obscureText: secret, decoration: InputDecoration(labelText: label)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('CANCEL')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, ctrl.text.trim()), child: const Text('SAVE')),
        ],
      ),
    );
  }

  Future<void> _chooseGoal(BuildContext context, WidgetRef ref, String current) async {
    final goal = await showDialog<String>(
      context: context,
      builder: (ctx) => SimpleDialog(
        backgroundColor: OsirisTheme.surface,
        title: const Text('Your goal'),
        children: [
          for (final g in goalLabels.keys)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(ctx, g),
              child: ListTile(
                title: Text(goalLabels[g]!),
                subtitle: Text(goalDescriptions[g]!),
                trailing: g == current ? const Icon(Icons.check) : null,
              ),
            ),
        ],
      ),
    );
    if (goal != null && context.mounted) await _update(context, ref, {'goal': goal});
  }

  Future<void> _export(BuildContext context, WidgetRef ref) async {
    try {
      final data = await ref.read(apiClientProvider).exportMyData();
      await Clipboard.setData(ClipboardData(text: const JsonEncoder.withIndent('  ').convert(data)));
      if (!context.mounted) return;
      final runs = (data['runs'] as List<dynamic>? ?? []).length;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('Your data ($runs runs and everything else) was copied as JSON. Paste it into a file to keep it.'),
      ));
    } catch (e) {
      if (context.mounted) _error(context, e);
    }
  }

  Future<void> _erase(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: OsirisTheme.surface,
        title: const Text('Erase your account?'),
        content: const Text('This deletes your routes, runs, badges, and profile. It cannot be undone. '
            'Other players keep their own results.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('KEEP MY ACCOUNT')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('ERASE', style: TextStyle(color: OsirisTheme.error)),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final password = await _ask(context, 'Confirm with your password', 'Password', secret: true);
    if (password == null || password.isEmpty || !context.mounted) return;
    try {
      await ref.read(apiClientProvider).eraseMyAccount(password);
      await ref.read(authProvider.notifier).logout();
      if (context.mounted) Navigator.of(context).popUntil((r) => r.isFirst);
    } catch (e) {
      if (context.mounted) _error(context, e);
    }
  }

  Future<void> _blocked(BuildContext context, WidgetRef ref) async {
    final api = ref.read(apiClientProvider);
    final blocks = await api.getBlocks();
    if (!context.mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: OsirisTheme.surface,
      builder: (ctx) => ListView(padding: const EdgeInsets.all(16), children: [
        const Text('Blocked players', style: TextStyle(fontSize: 18)),
        if (blocks.isEmpty) const Padding(padding: EdgeInsets.all(12), child: Text("You haven't blocked anyone.")),
        for (final b in blocks.cast<Map<String, dynamic>>())
          ListTile(
            title: Text(b['name'] as String),
            trailing: TextButton(
              onPressed: () async {
                await api.unblock(b['id'] as int);
                if (ctx.mounted) Navigator.pop(ctx);
              },
              child: const Text('UNBLOCK'),
            ),
          ),
      ]),
    );
  }

  Future<void> _rules(BuildContext context, WidgetRef ref) async {
    final rules = await ref.read(apiClientProvider).getRules();
    if (!context.mounted) return;
    const titles = {
      'rewards': 'Rewards and refunds',
      'referrals': 'Inviting friends',
      'verification': 'How runs are checked',
      'leaderboards': 'Leaderboards',
      'privacy': 'Privacy',
      'safety': 'Safety',
    };
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => Scaffold(
      appBar: AppBar(title: const Text('RULES')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        for (final entry in titles.entries) ...[
          Text(entry.value, style: Theme.of(context).textTheme.titleMedium),
          for (final line in (rules[entry.key] as List<dynamic>? ?? []).cast<String>())
            Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text('•  $line')),
          const SizedBox(height: 16),
        ],
      ]),
    )));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(myProfileV2Provider);
    final referral = ref.watch(_referralProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('SETTINGS')),
      body: profile.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(ApiError.getMessage(e))),
        data: (p) => ListView(children: [
          const _Header('Profile'),
          ListTile(
            leading: const Icon(Icons.badge_outlined),
            title: Text(p.displayName),
            subtitle: const Text('Name others see'),
            onTap: () async {
              final name = await _ask(context, 'Your name', 'Name', initial: p.displayName);
              if (name != null && name.length >= 2 && context.mounted) await _update(context, ref, {'display_name': name});
            },
          ),
          ListTile(
            leading: const Icon(Icons.flag_circle_outlined),
            title: Text(goalLabels[p.goal] ?? p.goal),
            subtitle: Text('Goal  •  you are ${'aeiou'.contains(p.identity.isEmpty ? 'x' : p.identity[0]) ? 'an' : 'a'} ${p.identity}'),
            onTap: () => _chooseGoal(context, ref, p.goal),
          ),
          ListTile(
            leading: const Icon(Icons.location_city_outlined),
            title: Text(p.city ?? 'Not set'),
            subtitle: const Text('Home city, used for local rankings (never from GPS)'),
            onTap: () async {
              final city = await _ask(context, 'Home city', 'City, e.g. Bedford NS', initial: p.city ?? '');
              if (city != null && context.mounted) await _update(context, ref, {'city': city});
            },
          ),
          const _Header('Privacy'),
          SwitchListTile(
            value: p.locationConsent,
            onChanged: (v) => _update(context, ref, {'location_consent': v}),
            title: const Text('Location during runs'),
            subtitle: const Text('Needed to record and verify runs'),
          ),
          SwitchListTile(
            value: p.leaderboardOptIn,
            onChanged: (v) => _update(context, ref, {'leaderboard_opt_in': v}),
            title: const Text('Show my name on leaderboards'),
            subtitle: const Text('When off, you appear as "Private runner"'),
          ),
          SwitchListTile(
            value: p.publicProfile,
            onChanged: (v) => _update(context, ref, {'public_profile': v}),
            title: const Text('Public achievement page'),
            subtitle: const Text('Shows your rank, runs, and badges. Never your location.'),
          ),
          const ExerciseConsentTile(),
          const _Header('Invite friends'),
          referral.when(
            loading: () => const LinearProgressIndicator(),
            error: (e, _) => ListTile(title: Text(ApiError.getMessage(e))),
            data: (r) => Column(children: [
              ListTile(
                leading: const Icon(Icons.person_add_alt),
                title: Text('Your invite code: ${r.code}'),
                subtitle: Text('${r.rewarded} friends rewarded  •  ${r.pending} waiting for their first run'),
                trailing: IconButton(
                  tooltip: 'Copy invite link',
                  icon: const Icon(Icons.copy),
                  onPressed: () => ShareHelper.copy(context, ref,
                      'Join me on Osiris: daily running and walking quests. Use my code ${r.code}. ${r.url}',
                      kind: 'referral'),
                ),
              ),
              for (final rule in r.rules)
                Padding(
                  padding: const EdgeInsets.fromLTRB(72, 0, 16, 4),
                  child: Text(rule, style: const TextStyle(color: Colors.white60, fontSize: 12)),
                ),
            ]),
          ),
          const _Header('Safety'),
          ListTile(leading: const Icon(Icons.block), title: const Text('Blocked players'),
              onTap: () => _blocked(context, ref)),
          ListTile(leading: const Icon(Icons.rule), title: const Text('Rules, rewards, and verification'),
              onTap: () => _rules(context, ref)),
          const _Header('Account'),
          ListTile(
            leading: const Icon(Icons.devices_other),
            title: const Text('Sign out of all other devices'),
            onTap: () async {
              try {
                await ref.read(authProvider.notifier).signOutEverywhere();
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Other devices have been signed out.')));
                }
              } catch (e) {
                if (context.mounted) _error(context, e);
              }
            },
          ),
          ListTile(leading: const Icon(Icons.download_outlined), title: const Text('Download my data'),
              onTap: () => _export(context, ref)),
          ListTile(
            leading: const Icon(Icons.logout),
            title: const Text('Log out'),
            onTap: () async {
              await ref.read(authProvider.notifier).logout();
              if (context.mounted) Navigator.of(context).popUntil((r) => r.isFirst);
            },
          ),
          ListTile(
            leading: const Icon(Icons.delete_forever_outlined, color: OsirisTheme.error),
            title: const Text('Erase my account', style: TextStyle(color: OsirisTheme.error)),
            onTap: () => _erase(context, ref),
          ),
          const SizedBox(height: 24),
        ]),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final String text;

  const _Header(this.text);

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
        child: Text(text.toUpperCase(),
            style: const TextStyle(letterSpacing: 1.2, fontSize: 12, color: OsirisTheme.secondary)),
      );
}
