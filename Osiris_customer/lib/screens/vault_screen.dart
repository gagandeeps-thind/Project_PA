import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import '../theme.dart';

/// Vault screen showing claimed domains and crystal locking.
class VaultScreen extends ConsumerStatefulWidget {
  const VaultScreen({super.key});

  @override
  ConsumerState<VaultScreen> createState() => _VaultScreenState();
}

class _VaultScreenState extends ConsumerState<VaultScreen> {
  // In a full implementation, these would come from the API.
  // For now we show a placeholder based on user profile data.
  List<Map<String, dynamic>> _domains = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadDomains();
  }

  Future<void> _loadDomains() async {
    // Simulate loading domains — in production, call API
    await Future.delayed(const Duration(milliseconds: 500));
    setState(() {
      _loading = false;
      // Placeholder domains based on cumulative area
      final user = ref.read(authProvider);
      if (user != null && user.cumulativeArea > 0) {
        _domains = [
          {
            'name': 'Domain #1',
            'area': user.cumulativeArea,
            'vault_balance': user.manaCrystals ~/ 2,
            'protected': user.manaCrystals > 10,
          },
        ];
      }
    });
  }

  void _showLockDialog(Map<String, dynamic> domain) {
    final crystalCtrl = TextEditingController();
    final user = ref.read(authProvider);
    final availableCrystals = user?.manaCrystals ?? 0;

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: OsirisTheme.surface,
        title: const Text('Lock Crystals'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Available: $availableCrystals 💎'),
            const SizedBox(height: 12),
            TextField(
              controller: crystalCtrl,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Crystals to lock',
                prefixIcon: Icon(Icons.lock),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('CANCEL'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Crystals locked into vault! 🔒'),
                  backgroundColor: OsirisTheme.success,
                ),
              );
            },
            child: const Text('LOCK'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('THE VAULT')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                // ── Crystal Balance Header ──
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(20),
                  color: OsirisTheme.surface,
                  child: Column(
                    children: [
                      const Icon(
                        Icons.diamond,
                        size: 40,
                        color: OsirisTheme.secondary,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        '${user?.manaCrystals ?? 0}',
                        style: const TextStyle(
                          fontSize: 32,
                          fontWeight: FontWeight.bold,
                          color: OsirisTheme.secondary,
                        ),
                      ),
                      const Text(
                        'MANA CRYSTALS',
                        style: TextStyle(
                          color: Colors.white54,
                          letterSpacing: 2,
                        ),
                      ),
                    ],
                  ),
                ),

                // ── Domain List ──
                Expanded(
                  child: _domains.isEmpty
                      ? Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.landscape,
                                  size: 64, color: Colors.white24),
                              const SizedBox(height: 12),
                              const Text(
                                'No domains claimed yet.\nExplore the map to claim territory!',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                    color: Colors.white54, fontSize: 15),
                              ),
                            ],
                          ),
                        )
                      : ListView.builder(
                          padding: const EdgeInsets.all(12),
                          itemCount: _domains.length,
                          itemBuilder: (ctx, i) {
                            final d = _domains[i];
                            final isProtected = d['protected'] as bool;

                            return Card(
                              margin: const EdgeInsets.only(bottom: 12),
                              child: Padding(
                                padding: const EdgeInsets.all(16),
                                child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.start,
                                  children: [
                                    // Header
                                    Row(
                                      children: [
                                        Icon(
                                          isProtected
                                              ? Icons.shield
                                              : Icons.shield_outlined,
                                          color: isProtected
                                              ? OsirisTheme.success
                                              : Colors.white38,
                                        ),
                                        const SizedBox(width: 8),
                                        Expanded(
                                          child: Text(
                                            d['name'] as String,
                                            style: Theme.of(context)
                                                .textTheme
                                                .titleLarge,
                                          ),
                                        ),
                                        if (isProtected)
                                          Container(
                                            padding:
                                                const EdgeInsets.symmetric(
                                              horizontal: 8,
                                              vertical: 4,
                                            ),
                                            decoration: BoxDecoration(
                                              color: OsirisTheme.success
                                                  .withAlpha(51),
                                              borderRadius:
                                                  BorderRadius.circular(4),
                                            ),
                                            child: const Text(
                                              'PROTECTED',
                                              style: TextStyle(
                                                color: OsirisTheme.success,
                                                fontSize: 10,
                                                fontWeight: FontWeight.bold,
                                              ),
                                            ),
                                          ),
                                      ],
                                    ),
                                    const SizedBox(height: 12),

                                    // Stats
                                    Row(
                                      children: [
                                        _VaultStat(
                                          label: 'Area',
                                          value:
                                              '${(d['area'] as double).toStringAsFixed(2)} km²',
                                          icon: Icons.square_foot,
                                        ),
                                        const SizedBox(width: 20),
                                        _VaultStat(
                                          label: 'Vault Balance',
                                          value: '${d['vault_balance']} 💎',
                                          icon: Icons.account_balance,
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 12),

                                    // Lock button
                                    SizedBox(
                                      width: double.infinity,
                                      child: OutlinedButton.icon(
                                        onPressed: () =>
                                            _showLockDialog(d),
                                        icon: const Icon(Icons.lock,
                                            color: OsirisTheme.secondary),
                                        label: const Text(
                                          'LOCK CRYSTALS',
                                          style: TextStyle(
                                              color:
                                                  OsirisTheme.secondary),
                                        ),
                                        style: OutlinedButton.styleFrom(
                                          side: const BorderSide(
                                              color:
                                                  OsirisTheme.secondary),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
                ),
              ],
            ),
    );
  }
}

class _VaultStat extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;

  const _VaultStat({
    required this.label,
    required this.value,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: Colors.white54),
        const SizedBox(width: 4),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style:
                    const TextStyle(color: Colors.white54, fontSize: 11)),
            Text(value,
                style: const TextStyle(fontWeight: FontWeight.bold)),
          ],
        ),
      ],
    );
  }
}
