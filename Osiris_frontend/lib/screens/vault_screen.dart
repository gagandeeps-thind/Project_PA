import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers.dart';
import '../theme.dart';
import '../api/api_error.dart';

class VaultScreen extends ConsumerStatefulWidget {
  const VaultScreen({super.key});

  @override
  ConsumerState<VaultScreen> createState() => _VaultScreenState();
}

class _VaultScreenState extends ConsumerState<VaultScreen> {
  final _domainIdController = TextEditingController();
  final _amountController = TextEditingController();
  bool _isLocking = false;

  Future<void> _handleLockVault() async {
    setState(() => _isLocking = true);
    try {
      final domainId = int.tryParse(_domainIdController.text);
      final amount = int.tryParse(_amountController.text);
      
      if (domainId == null || amount == null) {
        throw Exception("Invalid input format.");
      }

      final userProfile = ref.read(authProvider);
      
      final response = await ref.read(apiClientProvider).dio.post(
        '/api/v1/domains/$domainId/vault', 
        data: {
          'user_id': userProfile!.id,
          'amount': amount,
        }
      );

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(response.data['message']),
          backgroundColor: Colors.green,
        ));
      }
      
      // Refresh User Profile
      ref.read(authProvider.notifier).build();

    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Failed to lock vault: ${ApiError.getMessage(e)}'),
          backgroundColor: AppTheme.error,
        ));
      }
    } finally {
      if (mounted) setState(() => _isLocking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final userProfile = ref.watch(authProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('THE VAULT')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Balance Card
            Card(
              color: AppTheme.surface,
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  children: [
                    const Icon(Icons.diamond, color: AppTheme.secondary, size: 64),
                    const SizedBox(height: 16),
                    const Text('MANA CRYSTALS', style: TextStyle(color: AppTheme.textSecondary, letterSpacing: 2)),
                    const SizedBox(height: 8),
                    Text(
                      '${userProfile?.manaCrystals ?? 0}',
                      style: Theme.of(context).textTheme.displayLarge?.copyWith(color: AppTheme.primary),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 32),
            
            // Domain Protection Mock UI
            const Text('PROTECT DOMAIN', style: TextStyle(color: AppTheme.secondary, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            const Text(
              'Lock Mana Crystals into a Domain\'s Vault to set its Challenger Match. (Phase 1: Enter ID manually)',
              style: TextStyle(color: AppTheme.textSecondary, fontSize: 12),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _domainIdController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Domain ID', prefixIcon: Icon(Icons.map)),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _amountController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Target Vault Balance', prefixIcon: Icon(Icons.lock)),
            ),
            const SizedBox(height: 24),
            
            _isLocking
              ? const Center(child: CircularProgressIndicator())
              : ElevatedButton.icon(
                  onPressed: _handleLockVault,
                  icon: const Icon(Icons.security),
                  label: const Text('LOCK CRYSTALS'),
                  style: ElevatedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
                )
          ],
        ),
      ),
    );
  }
}
