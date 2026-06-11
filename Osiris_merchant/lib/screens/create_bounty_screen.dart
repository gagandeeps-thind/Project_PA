import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../theme.dart';
import '../providers.dart';
import '../api/api_error.dart';

/// Form screen to create a new merchant_chest bounty.
class CreateBountyScreen extends ConsumerStatefulWidget {
  const CreateBountyScreen({super.key});

  @override
  ConsumerState<CreateBountyScreen> createState() => _CreateBountyScreenState();
}

class _CreateBountyScreenState extends ConsumerState<CreateBountyScreen> {
  final _formKey = GlobalKey<FormState>();
  final _titleController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _latController = TextEditingController();
  final _lngController = TextEditingController();
  final _radiusController = TextEditingController(text: '30');
  final _couponTextController = TextEditingController();
  final _xpRewardController = TextEditingController(text: '100');
  final _crystalRewardController = TextEditingController(text: '5');
  final _maxCompletionsController = TextEditingController(text: '50');

  bool _isSubmitting = false;
  String? _errorMessage;

  @override
  void dispose() {
    _titleController.dispose();
    _descriptionController.dispose();
    _latController.dispose();
    _lngController.dispose();
    _radiusController.dispose();
    _couponTextController.dispose();
    _xpRewardController.dispose();
    _crystalRewardController.dispose();
    _maxCompletionsController.dispose();
    super.dispose();
  }

  Future<void> _handleSubmit() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });

    try {
      final merchant = ref.read(authProvider);
      if (merchant == null) throw Exception('Not authenticated');

      final client = ref.read(apiClientProvider);
      await client.createBounty({
        'title': _titleController.text.trim(),
        'description': _descriptionController.text.trim(),
        'target_lat': double.parse(_latController.text.trim()),
        'target_lng': double.parse(_lngController.text.trim()),
        'radius_m': double.parse(_radiusController.text.trim()),
        'coupon_text': _couponTextController.text.trim(),
        'xp_reward': int.parse(_xpRewardController.text.trim()),
        'crystal_reward': int.parse(_crystalRewardController.text.trim()),
        'max_completions': int.parse(_maxCompletionsController.text.trim()),
        'merchant_id': merchant.id,
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('✓ Bounty created successfully!'),
            backgroundColor: MerchantTheme.success,
          ),
        );
        Navigator.pop(context);
      }
    } catch (e) {
      setState(() => _errorMessage = ApiError.getMessage(e));
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('CREATE BOUNTY'),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            // ── Info Header ──
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: MerchantTheme.primary.withAlpha(12),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: MerchantTheme.primary.withAlpha(40)),
              ),
              child: const Row(
                children: [
                  Icon(Icons.info_outline,
                      color: MerchantTheme.primary, size: 20),
                  SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Create a Merchant Chest bounty. Players who reach the target location earn your coupon.',
                      style: TextStyle(
                          fontSize: 12, color: MerchantTheme.textSecondary),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // ── Title ──
            _buildLabel('Bounty Title'),
            const SizedBox(height: 8),
            TextFormField(
              controller: _titleController,
              decoration: const InputDecoration(
                hintText: 'e.g. Morning Run Challenge',
              ),
              validator: (v) =>
                  v == null || v.trim().isEmpty ? 'Title is required' : null,
            ),
            const SizedBox(height: 20),

            // ── Description ──
            _buildLabel('Description'),
            const SizedBox(height: 8),
            TextFormField(
              controller: _descriptionController,
              maxLines: 3,
              decoration: const InputDecoration(
                hintText: 'Describe what players need to do…',
              ),
              validator: (v) => v == null || v.trim().isEmpty
                  ? 'Description is required'
                  : null,
            ),
            const SizedBox(height: 20),

            // ── Location ──
            _buildLabel('Target Location'),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    controller: _latController,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true, signed: true),
                    decoration: const InputDecoration(
                      labelText: 'Latitude',
                      hintText: '40.7128',
                    ),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) {
                        return 'Required';
                      }
                      if (double.tryParse(v.trim()) == null) {
                        return 'Invalid';
                      }
                      return null;
                    },
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    controller: _lngController,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true, signed: true),
                    decoration: const InputDecoration(
                      labelText: 'Longitude',
                      hintText: '-74.0060',
                    ),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) {
                        return 'Required';
                      }
                      if (double.tryParse(v.trim()) == null) {
                        return 'Invalid';
                      }
                      return null;
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),

            // ── Radius ──
            _buildLabel('Radius (meters)'),
            const SizedBox(height: 8),
            TextFormField(
              controller: _radiusController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                hintText: '30',
                suffixText: 'm',
              ),
              validator: (v) {
                if (v == null || v.trim().isEmpty) return 'Required';
                final n = double.tryParse(v.trim());
                if (n == null || n <= 0) return 'Must be > 0';
                return null;
              },
            ),
            const SizedBox(height: 20),

            // ── Coupon Text ──
            _buildLabel('Coupon Reward Text'),
            const SizedBox(height: 8),
            TextFormField(
              controller: _couponTextController,
              decoration: const InputDecoration(
                hintText: 'e.g. 20% off protein smoothie',
                prefixIcon:
                    Icon(Icons.local_offer, color: MerchantTheme.textSecondary),
              ),
            ),
            const SizedBox(height: 20),

            // ── Rewards ──
            _buildLabel('Player Rewards'),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    controller: _xpRewardController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'XP',
                      hintText: '100',
                    ),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return 'Required';
                      if (int.tryParse(v.trim()) == null) return 'Invalid';
                      return null;
                    },
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    controller: _crystalRewardController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Crystals',
                      hintText: '5',
                    ),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return 'Required';
                      if (int.tryParse(v.trim()) == null) return 'Invalid';
                      return null;
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),

            // ── Max Completions ──
            _buildLabel('Max Completions'),
            const SizedBox(height: 8),
            TextFormField(
              controller: _maxCompletionsController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                hintText: '50',
              ),
              validator: (v) {
                if (v == null || v.trim().isEmpty) return 'Required';
                final n = int.tryParse(v.trim());
                if (n == null || n < 1) return 'Must be ≥ 1';
                return null;
              },
            ),
            const SizedBox(height: 28),

            // ── Error ──
            if (_errorMessage != null) ...[
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: MerchantTheme.error.withAlpha(20),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: MerchantTheme.error.withAlpha(60)),
                ),
                child: Text(_errorMessage!,
                    style: const TextStyle(
                        color: MerchantTheme.error, fontSize: 13)),
              ),
              const SizedBox(height: 16),
            ],

            // ── Submit ──
            SizedBox(
              height: 52,
              child: ElevatedButton(
                onPressed: _isSubmitting ? null : _handleSubmit,
                child: _isSubmitting
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.5,
                          color: MerchantTheme.background,
                        ),
                      )
                    : const Text('CREATE BOUNTY'),
              ),
            ),
            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }

  Widget _buildLabel(String text) {
    return Text(
      text,
      style: const TextStyle(
        fontSize: 13,
        fontWeight: FontWeight.w700,
        color: MerchantTheme.textSecondary,
        letterSpacing: 0.5,
      ),
    );
  }
}
