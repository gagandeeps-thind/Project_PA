import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';
import '../providers.dart';
import '../services/location_service.dart';
import '../theme.dart';

class MapScreen extends ConsumerStatefulWidget {
  const MapScreen({super.key});

  @override
  ConsumerState<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends ConsumerState<MapScreen> {
  final LocationService _locationService = LocationService();
  final MapController _mapController = MapController();
  
  Position? _currentPosition;
  bool _isTracking = false;
  List<LatLng> _routePoints = [];
  StreamSubscription<Position>? _positionStreamSub;
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    _initLocation();
  }

  @override
  void dispose() {
    _positionStreamSub?.cancel();
    super.dispose();
  }

  Future<void> _initLocation() async {
    try {
      final pos = await _locationService.getCurrentLocation();
      setState(() {
        _currentPosition = pos;
      });
      _mapController.move(LatLng(pos.latitude, pos.longitude), 16.0);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
      }
    }
  }

  void _toggleTracking() {
    if (_isTracking) {
      _stopTrackingAndCloseDomain();
    } else {
      _startTracking();
    }
  }

  void _startTracking() {
    if (_currentPosition == null) return;
    
    setState(() {
      _isTracking = true;
      _routePoints = [LatLng(_currentPosition!.latitude, _currentPosition!.longitude)];
    });

    _positionStreamSub = _locationService.getLocationStream().listen((Position position) {
      setState(() {
        _currentPosition = position;
        _routePoints.add(LatLng(position.latitude, position.longitude));
      });
      _mapController.move(LatLng(position.latitude, position.longitude), 18.0);
    });
  }

  Future<void> _stopTrackingAndCloseDomain() async {
    _positionStreamSub?.cancel();
    
    if (_routePoints.length < 3) {
      _cancelDomain("Domain too small. You need to walk a proper path.");
      return;
    }

    final start = _routePoints.first;
    final end = _routePoints.last;
    final distance = _locationService.distanceBetween(start.latitude, start.longitude, end.latitude, end.longitude);

    if (distance > 20.0) {
      _cancelDomain("Domain closure failed. You must return to your starting point (within 20m). You are ${distance.toStringAsFixed(1)}m away.");
      return;
    }

    // Success - Ask for Defense Feat
    _promptForDefenseFeat();
  }

  void _cancelDomain(String reason) {
    setState(() {
      _isTracking = false;
      _routePoints.clear();
    });
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(reason),
      backgroundColor: AppTheme.error,
    ));
  }

  Future<void> _promptForDefenseFeat() async {
    final scoreController = TextEditingController();
    String selectedType = 'pushups';

    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setDialogState) {
            return AlertDialog(
              backgroundColor: AppTheme.surface,
              title: const Text('Domain Closed! DEFENSE FEAT', style: TextStyle(color: AppTheme.primary)),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text('Perform an activity to set your Domain Defense Score.'),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    value: selectedType,
                    dropdownColor: AppTheme.background,
                    items: const [
                      DropdownMenuItem(value: 'pushups', child: Text('Pushups')),
                      DropdownMenuItem(value: 'squats', child: Text('Squats')),
                      DropdownMenuItem(value: 'sprint', child: Text('Sprint')),
                    ],
                    onChanged: (val) => setDialogState(() => selectedType = val!),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: scoreController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Score (e.g. reps)'),
                  ),
                ],
              ),
              actions: [
                TextButton(
                  onPressed: () {
                    Navigator.pop(context);
                    _cancelDomain("Domain abandoned.");
                  },
                  child: const Text('Abandon', style: TextStyle(color: AppTheme.error)),
                ),
                ElevatedButton(
                  onPressed: () {
                    Navigator.pop(context);
                    _submitDomain(selectedType, int.tryParse(scoreController.text) ?? 0);
                  },
                  child: const Text('SUBMIT DOMAIN'),
                ),
              ],
            );
          }
        );
      }
    );
  }

  Future<void> _submitDomain(String defenseType, int score) async {
    setState(() => _isSubmitting = true);
    final userProfile = ref.read(authProvider);
    if (userProfile == null) return;

    final coordinates = _routePoints.map((pt) => {
      'lat': pt.latitude,
      'lng': pt.longitude,
      'timestamp': DateTime.now().toUtc().toIso8601String(), // Mocking timestamp for each point since we didn't store it during stream
    }).toList();

    try {
      final response = await ref.read(apiClientProvider).submitDomain({
        'owner_id': userProfile.id,
        'coordinates': coordinates,
        'defense_score': score,
        'defense_type': defenseType,
        'device_timestamp': DateTime.now().toUtc().toIso8601String(),
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(response['message'] ?? 'Domain secured!'),
          backgroundColor: Colors.green,
        ));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Failed: $e'),
          backgroundColor: AppTheme.error,
        ));
      }
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
          _isTracking = false;
          _routePoints.clear();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('DOMAIN EXPANSION')),
      body: Stack(
        children: [
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              center: _currentPosition != null ? LatLng(_currentPosition!.latitude, _currentPosition!.longitude) : const LatLng(0, 0),
              zoom: 16.0,
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.example.osiris_frontend',
                // Optional: apply dark mode filtering to OpenStreetMap tiles
                tileBuilder: _darkModeTileBuilder,
              ),
              PolylineLayer(
                polylines: [
                  Polyline(
                    points: _routePoints,
                    strokeWidth: 4.0,
                    color: AppTheme.primary,
                  ),
                ],
              ),
              if (_currentPosition != null)
                MarkerLayer(
                  markers: [
                    Marker(
                      point: LatLng(_currentPosition!.latitude, _currentPosition!.longitude),
                      width: 24,
                      height: 24,
                      builder: (ctx) => const Container(
                        decoration: BoxDecoration(
                          color: AppTheme.secondary,
                          shape: BoxShape.circle,
                          boxShadow: [BoxShadow(color: AppTheme.secondary, blurRadius: 8)],
                        ),
                      ),
                    ),
                  ],
                ),
            ],
          ),
          if (_isSubmitting)
            Container(
              color: Colors.black54,
              child: const Center(child: CircularProgressIndicator()),
            ),
        ],
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
      floatingActionButton: _isSubmitting ? null : FloatingActionButton.extended(
        onPressed: _toggleTracking,
        backgroundColor: _isTracking ? AppTheme.error : AppTheme.primary,
        icon: Icon(_isTracking ? Icons.stop : Icons.play_arrow),
        label: Text(_isTracking ? 'CLOSE DOMAIN' : 'START DOMAIN'),
      ),
    );
  }

  Widget _darkModeTileBuilder(BuildContext context, Widget tileWidget, Tile tile) {
    return ColorFiltered(
      colorFilter: const ColorFilter.matrix([
        -1,  0,  0, 0, 255,
         0, -1,  0, 0, 255,
         0,  0, -1, 0, 255,
         0,  0,  0, 1,   0,
      ]),
      child: tileWidget,
    );
  }
}
