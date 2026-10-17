import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../api/growth_models.dart';
import '../providers.dart';
import '../theme.dart';

/// Three short steps to a first quest: pick a goal, allow location during runs, create
/// the account. No weight, height, or BMI is asked for.
///
/// Route argument (optional): {'invite': token} or {'referral': code} from a shared link.
class OnboardingScreen extends ConsumerStatefulWidget {
  const OnboardingScreen({super.key});

  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _codeCtrl = TextEditingController();
  int _step = 0;
  String _goal = 'fitness';
  // Consent must be an affirmative choice (PIPEDA meaningful consent); never pre-ticked.
  bool _locationConsent = false;
  bool _loading = false;
  String? _inviteToken;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final arg = ModalRoute.of(context)?.settings.arguments;
      if (arg is Map) {
        _inviteToken = arg['invite'] as String?;
        final referral = arg['referral'] as String?;
        if (referral != null) _codeCtrl.text = referral;
      }
      ref.read(apiClientProvider).trackEvent('onboarding_viewed', installId: ref.read(installIdProvider));
    });
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    _codeCtrl.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);
    try {
      await ref.read(authProvider.notifier).register(
            email: _emailCtrl.text.trim(),
            password: _passwordCtrl.text,
            displayName: _nameCtrl.text.trim(),
            goal: _goal,
            locationConsent: _locationConsent,
            referralCode: _codeCtrl.text.trim(),
            inviteToken: _inviteToken,
          );
      if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(ApiError.getMessage(e)), backgroundColor: OsirisTheme.error),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Step ${_step + 1} of 3'),
        leading: _step == 0
            ? null
            : IconButton(tooltip: 'Back', icon: const Icon(Icons.arrow_back), onPressed: () => setState(() => _step--)),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 32),
          child: switch (_step) {
            0 => _goalStep(),
            1 => _consentStep(),
            _ => _accountStep(),
          },
        ),
      ),
    );
  }

  Widget _goalStep() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('What do you want from Osiris?', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 8),
        const Text('We use this to size your daily quest. You can change it any time.',
            style: TextStyle(color: Colors.white70)),
        const SizedBox(height: 20),
        for (final goal in goalLabels.keys)
          Card(
            color: _goal == goal ? OsirisTheme.primary.withValues(alpha: 0.25) : null,
            child: ListTile(
              title: Text(goalLabels[goal]!, style: const TextStyle(fontWeight: FontWeight.w600)),
              subtitle: Text(goalDescriptions[goal]!),
              trailing: _goal == goal ? const Icon(Icons.check_circle, color: OsirisTheme.secondary) : null,
              onTap: () => setState(() => _goal = goal),
            ),
          ),
        const SizedBox(height: 20),
        ElevatedButton(onPressed: () => setState(() => _step = 1), child: const Text('CONTINUE')),
      ],
    );
  }

  Widget _consentStep() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Your location, your control', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 16),
        const _Point(icon: Icons.directions_run, text: 'We use GPS only while you record a run, to check the distance and time.'),
        const _Point(icon: Icons.visibility_off, text: 'Nobody sees your route. Public maps show challenges as approximate markers.'),
        const _Point(icon: Icons.home_outlined, text: 'The first and last 150 m of a run are removed before it can become a course.'),
        const _Point(icon: Icons.delete_outline, text: 'Download or erase your data any time in Settings.'),
        const SizedBox(height: 12),
        SwitchListTile(
          value: _locationConsent,
          onChanged: (v) => setState(() => _locationConsent = v),
          title: const Text('Allow location during runs'),
          subtitle: const Text('Runs need it to be verified. You can change this later in Settings.'),
        ),
        const SizedBox(height: 20),
        ElevatedButton(onPressed: () => setState(() => _step = 2), child: const Text('CONTINUE')),
      ],
    );
  }

  Widget _accountStep() {
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Create your account', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 20),
          TextFormField(
            controller: _nameCtrl,
            decoration: const InputDecoration(labelText: 'Name others see', prefixIcon: Icon(Icons.badge_outlined)),
            maxLength: 30,
            validator: (v) => (v == null || v.trim().length < 2) ? 'At least 2 characters' : null,
          ),
          TextFormField(
            controller: _emailCtrl,
            keyboardType: TextInputType.emailAddress,
            decoration: const InputDecoration(labelText: 'Email', prefixIcon: Icon(Icons.email_outlined)),
            validator: (v) => (v == null || !v.contains('@')) ? 'Enter a valid email' : null,
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _passwordCtrl,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'Password', prefixIcon: Icon(Icons.lock_outline)),
            validator: (v) => (v == null || v.length < 8) ? 'At least 8 characters' : null,
          ),
          const SizedBox(height: 12),
          if (_inviteToken == null)
            TextFormField(
              controller: _codeCtrl,
              textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(
                labelText: 'Invite code (optional)',
                prefixIcon: Icon(Icons.group_add_outlined),
              ),
            )
          else
            const Card(child: ListTile(leading: Icon(Icons.mail_outline), title: Text("You're joining from a friend's invite"))),
          const SizedBox(height: 24),
          ElevatedButton(
            onPressed: _loading ? null : _create,
            child: _loading
                ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('START MY FIRST QUEST'),
          ),
        ],
      ),
    );
  }
}

class _Point extends StatelessWidget {
  final IconData icon;
  final String text;

  const _Point({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: OsirisTheme.secondary),
          const SizedBox(width: 12),
          Expanded(child: Text(text)),
        ],
      ),
    );
  }
}
