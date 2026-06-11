import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../theme.dart';
import '../providers.dart';
import '../api/api_error.dart';
import '../api/models.dart';
import 'bounty_management_screen.dart';
import 'create_bounty_screen.dart';
import 'coupon_scanner_screen.dart';
import 'analytics_screen.dart';

/// Main merchant dashboard — the hub after login.
/// Shows activation banner (if needed), KPIs, quick actions, and recent bounties.
class MerchantDashboardScreen extends ConsumerStatefulWidget {
  const MerchantDashboardScreen({super.key});

  @override
  ConsumerState<MerchantDashboardScreen> createState() =>
      _MerchantDashboardScreenState();
}

class _MerchantDashboardScreenState
    extends ConsumerState<MerchantDashboardScreen> {
  int _currentIndex = 0;

  @override
  Widget build(BuildContext context) {
    final screens = [
      const _DashboardBody(),
      const BountyManagementScreen(),
      const AnalyticsScreen(),
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Text('OSIRIS MERCHANT'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout_rounded),
            tooltip: 'Logout',
            onPressed: () => ref.read(authProvider.notifier).logout(),
          ),
        ],
      ),
      body: screens[_currentIndex],
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (i) => setState(() => _currentIndex = i),
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.dashboard_rounded),
            label: 'Dashboard',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.inventory_2_rounded),
            label: 'Bounties',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.analytics_rounded),
            label: 'Analytics',
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────
// Dashboard Body (index 0)
// ─────────────────────────────────────────────────────

class _DashboardBody extends ConsumerWidget {
  const _DashboardBody();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final merchant = ref.watch(authProvider);
    final bountiesAsync = ref.watch(merchantBountiesProvider);

    if (merchant == null) {
      return const Center(child: CircularProgressIndicator());
    }

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(merchantProfileProvider);
        ref.invalidate(merchantBountiesProvider);
      },
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Activation Banner ──
          if (!merchant.isActive) _ActivationBanner(merchant: merchant),

          // ── KPI Cards ──
          if (merchant.isActive) ...[
            bountiesAsync.when(
              data: (bounties) => _KpiGrid(bounties: bounties),
              loading: () => const Center(
                child: Padding(
                  padding: EdgeInsets.all(32),
                  child: CircularProgressIndicator(),
                ),
              ),
              error: (e, _) => _ErrorCard(message: ApiError.getMessage(e)),
            ),
            const SizedBox(height: 20),
          ],

          // ── Quick Actions ──
          _buildSectionHeader(context, 'Quick Actions'),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _QuickActionCard(
                  icon: Icons.add_box_rounded,
                  label: 'Create Bounty',
                  color: MerchantTheme.primary,
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                        builder: (_) => const CreateBountyScreen()),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _QuickActionCard(
                  icon: Icons.qr_code_scanner_rounded,
                  label: 'Scan Coupon',
                  color: MerchantTheme.success,
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                        builder: (_) => const CouponScannerScreen()),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),

          // ── Recent Bounties ──
          _buildSectionHeader(context, 'Recent Bounties'),
          const SizedBox(height: 12),
          bountiesAsync.when(
            data: (bounties) {
              if (bounties.isEmpty) {
                return Container(
                  decoration: MerchantTheme.glassCard,
                  padding: const EdgeInsets.all(32),
                  child: Column(
                    children: [
                      Icon(Icons.inventory_2_outlined,
                          size: 48, color: MerchantTheme.textSecondary.withAlpha(100)),
                      const SizedBox(height: 12),
                      const Text(
                        'No bounties yet',
                        style: TextStyle(color: MerchantTheme.textSecondary),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Create your first merchant chest to attract players!',
                        style: TextStyle(
                            color: MerchantTheme.textSecondary, fontSize: 12),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                );
              }
              final recent = bounties.take(5).toList();
              return Column(
                children: recent
                    .map((b) => Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: _RecentBountyCard(bounty: b),
                        ))
                    .toList(),
              );
            },
            loading: () => const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: CircularProgressIndicator(),
              ),
            ),
            error: (e, _) => _ErrorCard(message: ApiError.getMessage(e)),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(BuildContext context, String title) {
    return Text(
      title,
      style: Theme.of(context).textTheme.titleMedium?.copyWith(
            letterSpacing: 0.5,
          ),
    );
  }
}

// ─────────────────────────────────────────────────────
// Activation Banner (shown when merchant is inactive)
// ─────────────────────────────────────────────────────

class _ActivationBanner extends ConsumerStatefulWidget {
  final MerchantProfile merchant;
  const _ActivationBanner({required this.merchant});

  @override
  ConsumerState<_ActivationBanner> createState() => _ActivationBannerState();
}

class _ActivationBannerState extends ConsumerState<_ActivationBanner> {
  bool _isLoading = false;
  String? _paymentId;
  String? _statusMessage;

  Future<void> _payPilotFee() async {
    setState(() {
      _isLoading = true;
      _statusMessage = null;
    });
    try {
      final client = ref.read(apiClientProvider);
      final result = await client.createPaymentIntent(widget.merchant.id);
      setState(() {
        _paymentId = result['provider_payment_id'];
        _statusMessage =
            'Payment intent created: $_paymentId\nUse simulate buttons below for MVP testing.';
      });
    } catch (e) {
      setState(() => _statusMessage = ApiError.getMessage(e));
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _simulateWebhook(String status) async {
    if (_paymentId == null) {
      setState(
          () => _statusMessage = 'Create a payment intent first.');
      return;
    }
    setState(() {
      _isLoading = true;
      _statusMessage = null;
    });
    try {
      final client = ref.read(apiClientProvider);
      await client.simulatePaymentWebhook(
        merchantId: widget.merchant.id,
        providerPaymentId: _paymentId!,
        status: status,
      );
      setState(() => _statusMessage = 'Webhook simulated: $status');
      // Refresh profile to see updated activation state
      ref.invalidate(merchantProfileProvider);
      ref.invalidate(authProvider);
    } catch (e) {
      setState(() => _statusMessage = ApiError.getMessage(e));
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final feeStr = (widget.merchant.pilotFeeCents / 100).toStringAsFixed(2);

    return Container(
      margin: const EdgeInsets.only(bottom: 20),
      decoration: BoxDecoration(
        color: MerchantTheme.warning.withAlpha(15),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: MerchantTheme.warning.withAlpha(80)),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.warning_amber_rounded,
                  color: MerchantTheme.warning, size: 24),
              const SizedBox(width: 10),
              Text(
                'Account Not Activated',
                style: Theme.of(context)
                    .textTheme
                    .titleMedium
                    ?.copyWith(color: MerchantTheme.warning),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            'Payment Status: ${widget.merchant.paymentStatus}',
            style: const TextStyle(color: MerchantTheme.textSecondary),
          ),
          const SizedBox(height: 4),
          Text(
            'Pilot Fee: \$$feeStr',
            style: const TextStyle(color: MerchantTheme.textSecondary),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: _isLoading ? null : _payPilotFee,
              icon: const Icon(Icons.payment_rounded),
              label: Text(_isLoading ? 'Processing…' : 'PAY PILOT FEE'),
            ),
          ),
          if (_paymentId != null) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _isLoading
                        ? null
                        : () => _simulateWebhook('succeeded'),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: MerchantTheme.success),
                      foregroundColor: MerchantTheme.success,
                    ),
                    child: const Text('✓ Simulate Success'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton(
                    onPressed:
                        _isLoading ? null : () => _simulateWebhook('failed'),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: MerchantTheme.error),
                      foregroundColor: MerchantTheme.error,
                    ),
                    child: const Text('✗ Simulate Decline'),
                  ),
                ),
              ],
            ),
          ],
          if (_statusMessage != null) ...[
            const SizedBox(height: 12),
            Text(
              _statusMessage!,
              style: const TextStyle(
                  color: MerchantTheme.textSecondary, fontSize: 12),
            ),
          ],
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────
// KPI Grid
// ─────────────────────────────────────────────────────

class _KpiGrid extends StatelessWidget {
  final List<MerchantBounty> bounties;
  const _KpiGrid({required this.bounties});

  @override
  Widget build(BuildContext context) {
    final activeBounties = bounties.where((b) => b.isActive).length;
    final totalCompletions =
        bounties.fold<int>(0, (sum, b) => sum + b.completionsCount);
    final totalCoupons =
        bounties.fold<int>(0, (sum, b) => sum + b.couponsIssued);

    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 12,
      mainAxisSpacing: 12,
      childAspectRatio: 1.5,
      children: [
        _KpiCard(
          icon: Icons.inventory_2_rounded,
          label: 'Active Bounties',
          value: activeBounties.toString(),
          color: MerchantTheme.primary,
        ),
        _KpiCard(
          icon: Icons.check_circle_outline,
          label: 'Completions',
          value: totalCompletions.toString(),
          color: MerchantTheme.success,
        ),
        _KpiCard(
          icon: Icons.confirmation_number_outlined,
          label: 'Coupons Issued',
          value: totalCoupons.toString(),
          color: MerchantTheme.secondary,
        ),
        _KpiCard(
          icon: Icons.redeem_rounded,
          label: 'Redeemed',
          value: '—', // Phase 2: need redemption tracking
          color: MerchantTheme.warning,
        ),
      ],
    );
  }
}

class _KpiCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;
  const _KpiCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: MerchantTheme.glassCard,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, color: color, size: 24),
          const Spacer(),
          Text(
            value,
            style: TextStyle(
              fontSize: 26,
              fontWeight: FontWeight.w800,
              color: color,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: const TextStyle(
                fontSize: 11, color: MerchantTheme.textSecondary),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────
// Quick Action Card
// ─────────────────────────────────────────────────────

class _QuickActionCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  const _QuickActionCard({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: MerchantTheme.glassCard,
        padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
        child: Column(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: color.withAlpha(25),
              ),
              child: Icon(icon, color: color, size: 26),
            ),
            const SizedBox(height: 12),
            Text(
              label,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: color,
                letterSpacing: 0.5,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────
// Recent Bounty Card
// ─────────────────────────────────────────────────────

class _RecentBountyCard extends StatelessWidget {
  final MerchantBounty bounty;
  const _RecentBountyCard({required this.bounty});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: MerchantTheme.glassCard,
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(10),
              color: bounty.isActive
                  ? MerchantTheme.primary.withAlpha(20)
                  : MerchantTheme.textSecondary.withAlpha(20),
            ),
            child: Icon(
              Icons.inventory_2_rounded,
              color: bounty.isActive
                  ? MerchantTheme.primary
                  : MerchantTheme.textSecondary,
              size: 22,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  bounty.title,
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                    color: MerchantTheme.textPrimary,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Text(
                  '${bounty.completionsCount} completions · ${bounty.couponsIssued} coupons',
                  style: const TextStyle(
                      fontSize: 12, color: MerchantTheme.textSecondary),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: bounty.isActive
                  ? MerchantTheme.success.withAlpha(25)
                  : MerchantTheme.error.withAlpha(25),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              bounty.isActive ? 'ACTIVE' : 'ENDED',
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w800,
                color: bounty.isActive
                    ? MerchantTheme.success
                    : MerchantTheme.error,
                letterSpacing: 1,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────
// Error Card (reusable)
// ─────────────────────────────────────────────────────

class _ErrorCard extends StatelessWidget {
  final String message;
  const _ErrorCard({required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: MerchantTheme.error.withAlpha(15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: MerchantTheme.error.withAlpha(60)),
      ),
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: MerchantTheme.error, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(message,
                style: const TextStyle(color: MerchantTheme.error, fontSize: 13)),
          ),
        ],
      ),
    );
  }
}
