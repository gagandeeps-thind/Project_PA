import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import '../providers.dart';
import '../services/location_service.dart';
import '../theme.dart';

class BountyBoardScreen extends ConsumerStatefulWidget {
  const BountyBoardScreen({super.key});

  @override
  ConsumerState<BountyBoardScreen> createState() => _BountyBoardScreenState();
}

class _BountyBoardScreenState extends ConsumerState<BountyBoardScreen> {
  final LocationService _locationService = LocationService();
  bool _isLoading = true;
  List<dynamic> _bounties = [];
  Position? _currentPosition;

  @override
  void initState() {
    super.initState();
    _fetchBounties();
  }

  Future<void> _fetchBounties() async {
    setState(() => _isLoading = true);
    try {
      final pos = await _locationService.getCurrentLocation();
      _currentPosition = pos;

      final data = await ref.read(apiClientProvider).getNearbyBounties(
        lat: pos.latitude,
        lng: pos.longitude,
        radiusKm: 5.0,
      );

      setState(() {
        _bounties = data['items'] ?? data; // Depending on if FastAPI returns a list or a dict with 'items'
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Failed to load bounties: $e'),
          backgroundColor: AppTheme.error,
        ));
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('BOUNTY BOARD'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _fetchBounties,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _bounties.isEmpty
              ? Center(
                  child: Text(
                    'No bounties nearby.\nTry claiming land to spawn sieges!',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: AppTheme.textSecondary),
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: _bounties.length,
                  itemBuilder: (context, index) {
                    final bounty = _bounties[index];
                    return Card(
                      color: AppTheme.surface,
                      margin: const EdgeInsets.only(bottom: 16),
                      child: ListTile(
                        leading: CircleAvatar(
                          backgroundColor: AppTheme.primary.withOpacity(0.2),
                          child: Icon(
                            bounty['bounty_type'] == 'merchant_chest' ? Icons.storefront : Icons.stars,
                            color: AppTheme.primary,
                          ),
                        ),
                        title: Text(bounty['title'], style: const TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary)),
                        subtitle: Text(
                          '${bounty['xp_reward']} XP • ${bounty['crystal_reward']} Crystals\nDistance: ${bounty['distance_km'].toStringAsFixed(2)} km',
                          style: const TextStyle(color: AppTheme.secondary),
                        ),
                        trailing: const Icon(Icons.chevron_right, color: AppTheme.textSecondary),
                        onTap: () {
                          if (_currentPosition != null) {
                            Navigator.pushNamed(context, '/bounty_detail', arguments: {
                              'bounty': bounty,
                              'currentPos': _currentPosition,
                            });
                          }
                        },
                      ),
                    );
                  },
                ),
    );
  }
}
