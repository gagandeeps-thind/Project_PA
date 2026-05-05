import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers.dart';
import '../theme.dart';

// A simple FutureProvider to fetch the revenue data
final revenueProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final apiClient = ref.watch(apiClientProvider);
  return apiClient.getPlatformRevenue();
});

class AdminDashboardScreen extends ConsumerWidget {
  const AdminDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final revenueAsync = ref.watch(revenueProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('ADMIN PORTAL (DEBUG)'),
        backgroundColor: AppTheme.surface,
      ),
      body: revenueAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, stack) => Center(
          child: Text('Failed to load revenue: $err', style: const TextStyle(color: AppTheme.error)),
        ),
        data: (data) {
          final totalCrystals = data['total_crystals'] ?? 0;
          final rowCount = data['row_count'] ?? 0;
          final bySource = data['by_source'] as Map<String, dynamic>? ?? {};

          return Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _buildSummaryCard(totalCrystals, rowCount),
                const SizedBox(height: 24),
                const Text(
                  'REVENUE BY SOURCE',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: AppTheme.primary,
                    letterSpacing: 1.2,
                  ),
                ),
                const SizedBox(height: 16),
                Expanded(
                  child: bySource.isEmpty
                      ? const Center(child: Text('No revenue data yet.', style: TextStyle(color: Colors.white54)))
                      : ListView.builder(
                          itemCount: bySource.length,
                          itemBuilder: (context, index) {
                            final key = bySource.keys.elementAt(index);
                            final value = bySource[key];
                            return Card(
                              color: AppTheme.surface,
                              margin: const EdgeInsets.only(bottom: 8),
                              child: ListTile(
                                leading: const Icon(Icons.account_balance_wallet, color: AppTheme.secondary),
                                title: Text(key, style: const TextStyle(fontWeight: FontWeight.bold)),
                                trailing: Text(
                                  '+$value 💎',
                                  style: const TextStyle(color: AppTheme.primary, fontSize: 16, fontWeight: FontWeight.bold),
                                ),
                              ),
                            );
                          },
                        ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildSummaryCard(int totalCrystals, int rowCount) {
    return Card(
      color: AppTheme.surface,
      shape: RoundedRectangleBorder(
        side: const BorderSide(color: AppTheme.primary, width: 2),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          children: [
            const Text(
              'PLATFORM LEDGER',
              style: TextStyle(color: Colors.white54, letterSpacing: 2),
            ),
            const SizedBox(height: 16),
            Text(
              '$totalCrystals 💎',
              style: const TextStyle(
                fontSize: 48,
                fontWeight: FontWeight.bold,
                color: AppTheme.primary,
                shadows: [Shadow(color: AppTheme.primary, blurRadius: 10)],
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Total system earnings across $rowCount events',
              style: const TextStyle(color: Colors.white70),
            ),
          ],
        ),
      ),
    );
  }
}
