import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../theme.dart';
import '../providers.dart';
import '../api/api_error.dart';
import '../api/models.dart';

/// Analytics screen showing bounty performance overview and breakdown.
class AnalyticsScreen extends ConsumerWidget {
  const AnalyticsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bountiesAsync = ref.watch(merchantBountiesProvider);

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(merchantBountiesProvider),
      child: bountiesAsync.when(
        data: (bounties) => _AnalyticsBody(bounties: bounties),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.error_outline,
                    color: MerchantTheme.error, size: 48),
                const SizedBox(height: 16),
                Text(
                  ApiError.getMessage(e),
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: MerchantTheme.textSecondary),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AnalyticsBody extends StatelessWidget {
  final List<MerchantBounty> bounties;
  const _AnalyticsBody({required this.bounties});

  @override
  Widget build(BuildContext context) {
    final totalBounties = bounties.length;
    final activeBounties = bounties.where((b) => b.isActive).length;
    final inactiveBounties = totalBounties - activeBounties;
    final totalCompletions =
        bounties.fold<int>(0, (sum, b) => sum + b.completionsCount);
    final totalCoupons =
        bounties.fold<int>(0, (sum, b) => sum + b.couponsIssued);
    final avgCompletions =
        totalBounties > 0 ? (totalCompletions / totalBounties) : 0.0;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // ── Overview Header ──
        Text(
          'Performance Overview',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 16),

        // ── Summary Cards ──
        Container(
          decoration: MerchantTheme.glassCardAccent,
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              Row(
                children: [
                  _OverviewStat(
                    label: 'Total Bounties',
                    value: totalBounties.toString(),
                    icon: Icons.inventory_2_rounded,
                    color: MerchantTheme.primary,
                  ),
                  _OverviewStat(
                    label: 'Active',
                    value: activeBounties.toString(),
                    icon: Icons.play_circle_outline,
                    color: MerchantTheme.success,
                  ),
                  _OverviewStat(
                    label: 'Ended',
                    value: inactiveBounties.toString(),
                    icon: Icons.stop_circle_outlined,
                    color: MerchantTheme.textSecondary,
                  ),
                ],
              ),
              const SizedBox(height: 16),
              const Divider(color: MerchantTheme.divider),
              const SizedBox(height: 16),
              Row(
                children: [
                  _OverviewStat(
                    label: 'Total Completions',
                    value: totalCompletions.toString(),
                    icon: Icons.check_circle_outline,
                    color: MerchantTheme.success,
                  ),
                  _OverviewStat(
                    label: 'Coupons Issued',
                    value: totalCoupons.toString(),
                    icon: Icons.confirmation_number_outlined,
                    color: MerchantTheme.secondary,
                  ),
                  _OverviewStat(
                    label: 'Avg / Bounty',
                    value: avgCompletions.toStringAsFixed(1),
                    icon: Icons.trending_up_rounded,
                    color: MerchantTheme.warning,
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 28),

        // ── Performance Breakdown ──
        Text(
          'Bounty Breakdown',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),

        if (bounties.isEmpty)
          Container(
            decoration: MerchantTheme.glassCard,
            padding: const EdgeInsets.all(32),
            child: const Center(
              child: Text(
                'No data yet. Create bounties to see analytics.',
                style: TextStyle(color: MerchantTheme.textSecondary),
                textAlign: TextAlign.center,
              ),
            ),
          )
        else
          ...bounties.map((b) => _BountyBreakdownCard(bounty: b)),
      ],
    );
  }
}

class _OverviewStat extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;
  const _OverviewStat({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(height: 8),
          Text(
            value,
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w800,
              color: color,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: const TextStyle(
                fontSize: 10, color: MerchantTheme.textSecondary),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

class _BountyBreakdownCard extends StatelessWidget {
  final MerchantBounty bounty;
  const _BountyBreakdownCard({required this.bounty});

  @override
  Widget build(BuildContext context) {
    final maxCompletions =
        bounty.completionsCount + bounty.completionsRemaining;
    final pct = maxCompletions > 0
        ? (bounty.completionsCount / maxCompletions)
        : 0.0;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: MerchantTheme.glassCard,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  bounty.title,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: MerchantTheme.textPrimary,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: bounty.isActive
                      ? MerchantTheme.success.withAlpha(20)
                      : MerchantTheme.textSecondary.withAlpha(20),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  bounty.isActive ? 'ACTIVE' : 'ENDED',
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w800,
                    color: bounty.isActive
                        ? MerchantTheme.success
                        : MerchantTheme.textSecondary,
                    letterSpacing: 1,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          // Progress bar
          Row(
            children: [
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(3),
                  child: LinearProgressIndicator(
                    value: pct,
                    backgroundColor: MerchantTheme.divider,
                    valueColor: const AlwaysStoppedAnimation<Color>(
                        MerchantTheme.primary),
                    minHeight: 6,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Text(
                '${(pct * 100).toInt()}%',
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: MerchantTheme.primary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          // Stats row
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _MiniStat(
                  label: 'Completions',
                  value: '${bounty.completionsCount}/$maxCompletions'),
              _MiniStat(
                  label: 'Coupons', value: bounty.couponsIssued.toString()),
              _MiniStat(
                  label: 'Radius', value: '${bounty.radiusM.toInt()}m'),
            ],
          ),
        ],
      ),
    );
  }
}

class _MiniStat extends StatelessWidget {
  final String label;
  final String value;
  const _MiniStat({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
              fontSize: 10, color: MerchantTheme.textSecondary),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          style: const TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w700,
            color: MerchantTheme.textPrimary,
          ),
        ),
      ],
    );
  }
}
