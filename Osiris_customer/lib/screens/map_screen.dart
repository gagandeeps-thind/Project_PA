import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../api/api_error.dart';
import '../providers.dart';
import '../services/location_service.dart';
import '../services/pedometer_service.dart';
import '../theme.dart';

/// Map screen for domain tracing, nearby domain/bounty display, and pedometer overlay.
class MapScreen extends ConsumerStatefulWidget {
  const MapScreen({super.key});

  @override
  ConsumerState<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends ConsumerState<MapScreen> {
  final MapController _mapCtrl = MapController();
  final PedometerService _pedometer = PedometerService();

  LatLng? _currentPos;
  StreamSubscription<Position>? _locationSub;

  // Domain tracing state
  bool _isTracing = false;
  final List<LatLng> _tracePath = [];

  // Nearby data
  List<Map<String, dynamic>> _nearbyDomains = [];
  List<Map<String, dynamic>> _nearbyBounties = [];

  // Pedometer display
  int _steps = 0;
  double _cadence = 0.0;

  bool _loadingLocation = true;

  @override
  void initState() {
    super.initState();
    _initLocation();
  }

  @override
  void dispose() {
    _locationSub?.cancel();
    _pedometer.dispose();
    super.dispose();
  }

  Future<void> _initLocation() async {
    try {
      final pos = await LocationService.getCurrentLocation();
      setState(() {
        _currentPos = LatLng(pos.latitude, pos.longitude);
        _loadingLocation = false;
      });

      _mapCtrl.move(_currentPos!, 16);
      _fetchNearbyData();

      // Live tracking
      _locationSub = LocationService.getLocationStream().listen((pos) {
        final newPos = LatLng(pos.latitude, pos.longitude);
        setState(() => _currentPos = newPos);

        if (_isTracing) {
          setState(() => _tracePath.add(newPos));
        }
      });
    } catch (e) {
      setState(() => _loadingLocation = false);
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

  Future<void> _fetchNearbyData() async {
    if (_currentPos == null) return;

    final api = ref.read(apiClientProvider);
    try {
      final domains = await api.getNearbyDomains(
        _currentPos!.latitude,
        _currentPos!.longitude,
        2.0,
      );
      final bounties = await api.getNearbyBounties(
        _currentPos!.latitude,
        _currentPos!.longitude,
        2.0,
      );

      setState(() {
        _nearbyDomains = domains.cast<Map<String, dynamic>>();
        _nearbyBounties = bounties.cast<Map<String, dynamic>>();
      });
    } catch (_) {
      // Silently continue — data is supplementary
    }
  }

  void _toggleTracing() {
    if (_isTracing) {
      // Stop tracing
      _pedometer.stop();
      setState(() => _isTracing = false);

      if (_tracePath.length >= 3) {
        _showSubmitDialog();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Need at least 3 points for a domain.')),
        );
      }
    } else {
      // Start tracing
      _tracePath.clear();
      if (_currentPos != null) _tracePath.add(_currentPos!);

      _pedometer.start(onStep: (steps, cadence) {
        setState(() {
          _steps = steps;
          _cadence = cadence;
        });
      });

      setState(() {
        _isTracing = true;
        _steps = 0;
        _cadence = 0.0;
      });
    }
  }

  Future<void> _showSubmitDialog() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: OsirisTheme.surface,
        title: const Text('Submit Domain?'),
        content: Text(
          'You traced ${_tracePath.length} points.\n'
          'Steps: $_steps\n'
          'Submit this domain to the Osiris network?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('CANCEL'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('SUBMIT'),
          ),
        ],
      ),
    );

    if (confirm == true) {
      await _submitDomain();
    }
  }

  Future<void> _submitDomain() async {
    final api = ref.read(apiClientProvider);
    final user = ref.read(authProvider);
    if (user == null) return;

    // Close polygon
    final closedPath = [..._tracePath, _tracePath.first];

    try {
      await api.submitDomain({
        'user_id': user.id,
        'coordinates': closedPath
            .map((p) => [p.longitude, p.latitude])
            .toList(),
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Domain submitted successfully! ⚔️'),
            backgroundColor: OsirisTheme.success,
          ),
        );
      }

      _fetchNearbyData();
    } catch (e) {
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('DOMAIN EXPANSION')),
      body: _loadingLocation
          ? const Center(child: CircularProgressIndicator())
          : Stack(
              children: [
                // ── Map ──
                FlutterMap(
                  mapController: _mapCtrl,
                  options: MapOptions(
                    initialCenter: _currentPos ?? const LatLng(0, 0),
                    initialZoom: 16,
                  ),
                  children: [
                    TileLayer(
                      urlTemplate:
                          'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                      userAgentPackageName: 'com.osiris.osiris_customer',
                    ),

                    // Current position marker
                    if (_currentPos != null)
                      MarkerLayer(
                        markers: [
                          Marker(
                            point: _currentPos!,
                            width: 20,
                            height: 20,
                            child: Container(
                              decoration: BoxDecoration(
                                color: OsirisTheme.primary,
                                shape: BoxShape.circle,
                                border: Border.all(
                                    color: Colors.white, width: 2),
                              ),
                            ),
                          ),
                        ],
                      ),

                    // Trace path polyline
                    if (_tracePath.isNotEmpty)
                      PolylineLayer(
                        polylines: [
                          Polyline(
                            points: _tracePath,
                            color: OsirisTheme.primary,
                            strokeWidth: 3,
                          ),
                        ],
                      ),

                    // Nearby domain polygons
                    if (_nearbyDomains.isNotEmpty)
                      PolygonLayer(
                        polygons: _nearbyDomains.map((d) {
                          final coords = d['coordinates'] as List? ?? [];
                          final points = coords
                              .map((c) =>
                                  LatLng((c[1] as num).toDouble(), (c[0] as num).toDouble()))
                              .toList();
                          return Polygon(
                            points: points,
                            color: OsirisTheme.secondary.withAlpha(51),
                            borderColor: OsirisTheme.secondary,
                            borderStrokeWidth: 2,
                          );
                        }).toList(),
                      ),

                    // Nearby bounty markers
                    if (_nearbyBounties.isNotEmpty)
                      MarkerLayer(
                        markers: _nearbyBounties.map((b) {
                          final lat = (b['latitude'] as num?)?.toDouble() ?? 0;
                          final lng = (b['longitude'] as num?)?.toDouble() ?? 0;
                          return Marker(
                            point: LatLng(lat, lng),
                            width: 30,
                            height: 30,
                            child: const Icon(
                              Icons.flag,
                              color: Colors.orange,
                              size: 28,
                            ),
                          );
                        }).toList(),
                      ),
                  ],
                ),

                // ── Pedometer Overlay ──
                if (_isTracing)
                  Positioned(
                    top: 12,
                    left: 12,
                    child: Card(
                      color: OsirisTheme.surface.withAlpha(230),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              '🚶 Steps: $_steps',
                              style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              '⚡ Cadence: ${_cadence.toStringAsFixed(1)} spm',
                              style: const TextStyle(fontSize: 14),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),

      // ── FAB: Start/Stop Tracing ──
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _toggleTracing,
        backgroundColor: _isTracing ? OsirisTheme.error : OsirisTheme.primary,
        icon: Icon(_isTracing ? Icons.stop : Icons.play_arrow),
        label: Text(_isTracing ? 'STOP' : 'TRACE DOMAIN'),
      ),
    );
  }
}
