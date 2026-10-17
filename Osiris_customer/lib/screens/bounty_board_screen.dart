import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../providers.dart';
import '../services/location_service.dart';
import '../theme.dart';

/// Bounty board listing nearby bounties for the player.
class BountyBoardScreen extends ConsumerStatefulWidget {
  const BountyBoardScreen({super.key});

  @override
  ConsumerState<BountyBoardScreen> createState() => _BountyBoardScreenState();
}

class _BountyBoardScreenState extends ConsumerState<BountyBoardScreen> {
  List<Map<String, dynamic>> _bounties = [];
  bool _loading = true;
  double? _userLat;
  double? _userLng;

  @override
  void initState() {
    super.initState();
    _fetchBounties();
  }

  Future<void> _fetchBounties() async {
    try {
      final pos = await LocationService.getCurrentLocation();
      _userLat = pos.latitude;
      _userLng = pos.longitude;

      final api = ref.read(apiClientProvider);
      final data = await api.getNearbyBounties(
        pos.latitude,
        pos.longitude,
        5.0,
      );

      setState(() {
        _bounties = data.cast<Map<String, dynamic>>();
        _loading = false;
      });
    } catch (e) {
      setState(() => _loading = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(ApiError.getMessage(e)),
            backgroundColor: OsirisTheme.error,
          ),
        );
      }
    }
  }

  String _formatDistance(Map<String, dynamic> bounty) {
    if (_userLat == null || _userLng == null) return '';
    final lat = (bounty['latitude'] as num?)?.toDouble();
    final lng = (bounty['longitude'] as num?)?.toDouble();
    if (lat == null || lng == null) return '';

    final meters = LocationService.distanceBetween(
      _userLat!,
      _userLng!,
      lat,
      lng,
    );

    if (meters < 1000) {
      return '${meters.round()}m away';
    }
    return '${(meters / 1000).toStringAsFixed(1)}km away';
  }

  Color _typeBadgeColor(String? type) {
    switch (type?.toLowerCase()) {
      case 'combat':
        return Colors.red;
      case 'exploration':
        return OsirisTheme.secondary;
      case 'merchant':
        return Colors.orange;
      default:
        return OsirisTheme.primary;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('BOUNTY BOARD'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: () {
              setState(() => _loading = true);
              _fetchBounties();
            },
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _bounties.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.search_off,
                          size: 64, color: Colors.white24),
                      const SizedBox(height: 12),
                      const Text(
                        'No bounties nearby',
                        style: TextStyle(color: Colors.white54, fontSize: 16),
                      ),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _fetchBounties,
                  child: ListView.builder(
                    padding: const EdgeInsets.all(12),
                    itemCount: _bounties.length,
                    itemBuilder: (ctx, i) {
                      final b = _bounties[i];
                      final type = b['type'] as String? ?? 'quest';
                      final title = b['title'] as String? ?? 'Unknown Bounty';
                      final desc =
                          b['description'] as String? ?? 'No description';
                      final xpReward = b['xp_reward'] as int? ?? 0;
                      final crystalReward =
                          b['crystal_reward'] as int? ?? 0;

                      return Card(
                        margin: const EdgeInsets.only(bottom: 12),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(12),
                          onTap: () => Navigator.of(context).pushNamed(
                            '/bounty-detail',
                            arguments: b,
                          ),
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                // Title + type badge
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        title,
                                        style: Theme.of(context)
                                            .textTheme
                                            .titleLarge,
                                      ),
                                    ),
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 8,
                                        vertical: 4,
                                      ),
                                      decoration: BoxDecoration(
                                        color: _typeBadgeColor(type)
                                            .withAlpha(51),
                                        borderRadius:
                                            BorderRadius.circular(4),
                                        border: Border.all(
                                          color: _typeBadgeColor(type),
                                        ),
                                      ),
                                      child: Text(
                                        type.toUpperCase(),
                                        style: TextStyle(
                                          color: _typeBadgeColor(type),
                                          fontSize: 10,
                                          fontWeight: FontWeight.bold,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 8),

                                // Description
                                Text(
                                  desc,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                      color: Colors.white70),
                                ),
                                const SizedBox(height: 12),

                                // Reward + distance
                                Row(
                                  children: [
                                    Icon(Icons.star,
                                        size: 16,
                                        color: OsirisTheme.primary),
                                    const SizedBox(width: 4),
                                    Text('$xpReward XP'),
                                    const SizedBox(width: 12),
                                    Icon(Icons.diamond,
                                        size: 16,
                                        color: OsirisTheme.secondary),
                                    const SizedBox(width: 4),
                                    Text('$crystalReward'),
                                    const Spacer(),
                                    Text(
                                      _formatDistance(b),
                                      style: const TextStyle(
                                        color: Colors.white54,
                                        fontSize: 12,
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
    );
  }
}
