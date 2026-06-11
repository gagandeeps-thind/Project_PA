import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../providers.dart';
import '../theme.dart';

/// Onboarding screen for new player registration.
class OnboardingScreen extends ConsumerStatefulWidget {
  const OnboardingScreen({super.key});

  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _weightCtrl = TextEditingController();
  final _heightCtrl = TextEditingController();
  String _selectedPath = 'Strength';
  bool _loading = false;

  static const _paths = ['Strength', 'Cardio', 'Balance'];

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    _weightCtrl.dispose();
    _heightCtrl.dispose();
    super.dispose();
  }

  Future<void> _handleRegister() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _loading = true);

    try {
      await ref.read(authProvider.notifier).register(
            _emailCtrl.text.trim(),
            _passwordCtrl.text,
            double.parse(_weightCtrl.text.trim()),
            double.parse(_heightCtrl.text.trim()),
            _selectedPath.toLowerCase(),
          );
      if (mounted) {
        // Pop back — AuthWrapper will redirect to dashboard
        Navigator.of(context).popUntil((r) => r.isFirst);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(ApiError.getMessage(e)),
            backgroundColor: OsirisTheme.error,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Begin Your Journey')),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.whatshot,
                    size: 56,
                    color: OsirisTheme.primary,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'CREATE YOUR AVATAR',
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                          color: OsirisTheme.primary,
                          letterSpacing: 2,
                        ),
                  ),
                  const SizedBox(height: 32),

                  // ── Email ──
                  TextFormField(
                    controller: _emailCtrl,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: 'Email',
                      prefixIcon: Icon(Icons.email_outlined),
                    ),
                    validator: (v) =>
                        v == null || v.isEmpty ? 'Enter your email' : null,
                  ),
                  const SizedBox(height: 16),

                  // ── Password ──
                  TextFormField(
                    controller: _passwordCtrl,
                    obscureText: true,
                    decoration: const InputDecoration(
                      labelText: 'Password',
                      prefixIcon: Icon(Icons.lock_outline),
                    ),
                    validator: (v) => v != null && v.length >= 6
                        ? null
                        : 'Min 6 characters',
                  ),
                  const SizedBox(height: 16),

                  // ── Weight ──
                  TextFormField(
                    controller: _weightCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Weight (kg)',
                      prefixIcon: Icon(Icons.fitness_center),
                    ),
                    validator: (v) {
                      if (v == null || v.isEmpty) return 'Enter weight';
                      final n = double.tryParse(v);
                      if (n == null || n <= 0) return 'Enter valid weight';
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),

                  // ── Height ──
                  TextFormField(
                    controller: _heightCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Height (m)',
                      prefixIcon: Icon(Icons.height),
                    ),
                    validator: (v) {
                      if (v == null || v.isEmpty) return 'Enter height';
                      final n = double.tryParse(v);
                      if (n == null || n <= 0) return 'Enter valid height';
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),

                  // ── Path Selection ──
                  DropdownButtonFormField<String>(
                    value: _selectedPath,
                    decoration: const InputDecoration(
                      labelText: 'Preferred Path',
                      prefixIcon: Icon(Icons.explore),
                    ),
                    dropdownColor: OsirisTheme.surface,
                    items: _paths
                        .map((p) => DropdownMenuItem(value: p, child: Text(p)))
                        .toList(),
                    onChanged: (v) {
                      if (v != null) setState(() => _selectedPath = v);
                    },
                  ),
                  const SizedBox(height: 32),

                  // ── Register Button ──
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: _loading ? null : _handleRegister,
                      child: _loading
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          : const Text('AWAKEN'),
                    ),
                  ),
                  const SizedBox(height: 16),

                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: Text(
                      'Already a player? Login',
                      style: TextStyle(color: OsirisTheme.secondary),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
