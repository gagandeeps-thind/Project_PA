import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../theme.dart';
import '../providers.dart';
import '../api/api_error.dart';
import '../api/models.dart';
import 'create_bounty_screen.dart';

/// Lists all merchant bounties with details and a FAB to create new ones.
class BountyManagementScreen extends ConsumerWidget {
  const BountyManagementScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bountiesAsync = ref.watch(merchantBountiesProvider);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(merchantBountiesProvider),
        child: bountiesAsync.when(
          data: (bounties) => _buildBountyList(context, bounties),
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
                  const SizedBox(height: 16),
                  OutlinedButton(
                    onPressed: () => ref.invalidate(merchantBountiesProvider),
                    child: const Text('Retry'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          await Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const CreateBountyScreen()),
          );
          // Refresh bounties after returning from create screen
          ref.invalidate(merchantBountiesProvider);
        },
        icon: const Icon(Icons.add),
        label: const Text('NEW BOUNTY'),
      ),
    );
  }

  Widget _buildBountyList(BuildContext context, List<MerchantBounty> bounties) {
    if (bounties.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.inventory_2_outlined,
                size: 64, color: MerchantTheme.textSecondary.withAlpha(80)),
            const SizedBox(height: 16),
            const Text(
              'No bounties yet',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: MerchantTheme.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Tap + to create your first merchant chest',
              style: TextStyle(color: MerchantTheme.textSecondary),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 80),
      itemCount: bounties.length,
      itemBuilder: (context, index) {
        final bounty = bounties[index];
        return _BountyDetailCard(bounty: bounty);
      },
    );
  }
}

class _BountyDetailCard extends StatelessWidget {
  final MerchantBounty bounty;
  const _BountyDetailCard({required this.bounty});

  @override
  Widget build(BuildContext context) {
    final completionPct = bounty.completionsRemaining > 0
        ? bounty.completionsCount /
            (bounty.completionsCount + bounty.completionsRemaining)
        : (bounty.completionsCount > 0 ? 1.0 : 0.0);

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: MerchantTheme.glassCard,
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Header Row ──
          Row(
            children: [
              Expanded(
                child: Text(
                  bounty.title,
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: MerchantTheme.textPrimary,
                  ),
                ),
              ),
              _StatusBadge(isActive: bounty.isActive),
            ],
          ),
          if (bounty.description.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              bounty.description,
              style: const TextStyle(
                  fontSize: 13, color: MerchantTheme.textSecondary),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          const SizedBox(height: 14),

          // ── Stats Row ──
          Row(
            children: [
              _StatChip(
                icon: Icons.check_circle_outline,
                label: 'Completions',
                value:
                    '${bounty.completionsCount} / ${bounty.completionsCount + bounty.completionsRemaining}',
                color: MerchantTheme.success,
              ),
              const SizedBox(width: 16),
              _StatChip(
                icon: Icons.confirmation_number_outlined,
                label: 'Coupons',
                value: bounty.couponsIssued.toString(),
                color: MerchantTheme.secondary,
              ),
              const SizedBox(width: 16),
              _StatChip(
                icon: Icons.radar_rounded,
                label: 'Radius',
                value: '${bounty.radiusM.toInt()}m',
                color: MerchantTheme.primary,
              ),
            ],
          ),
          const SizedBox(height: 12),

          // ── Progress Bar ──
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: completionPct,
              backgroundColor: MerchantTheme.divider,
              valueColor:
                  const AlwaysStoppedAnimation<Color>(MerchantTheme.primary),
              minHeight: 4,
            ),
          ),

          // ── Coupon Text ──
          if (bounty.couponText != null && bounty.couponText!.isNotEmpty) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: MerchantTheme.primary.withAlpha(12),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: MerchantTheme.primary.withAlpha(40)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.local_offer_rounded,
                      size: 16, color: MerchantTheme.primary),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      bounty.couponText!,
                      style: const TextStyle(
                          fontSize: 12, color: MerchantTheme.primary),
                    ),
                  ),
                ],
              ),
            ),
          ],

          // ── Location ──
          const SizedBox(height: 10),
          Text(
            'Location: (${bounty.targetLat.toStringAsFixed(4)}, ${bounty.targetLng.toStringAsFixed(4)})',
            style: const TextStyle(
                fontSize: 11, color: MerchantTheme.textSecondary),
          ),
        ],
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final bool isActive;
  const _StatusBadge({required this.isActive});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: isActive
            ? MerchantTheme.success.withAlpha(25)
            : MerchantTheme.error.withAlpha(25),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        isActive ? 'ACTIVE' : 'INACTIVE',
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w800,
          color:
              isActive ? MerchantTheme.success : MerchantTheme.error,
          letterSpacing: 1,
        ),
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;
  const _StatChip({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 14, color: color),
              const SizedBox(width: 4),
              Text(
                label,
                style: const TextStyle(
                    fontSize: 10, color: MerchantTheme.textSecondary),
              ),
            ],
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w700,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}
