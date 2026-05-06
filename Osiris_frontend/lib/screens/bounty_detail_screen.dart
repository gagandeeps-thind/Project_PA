import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import '../providers.dart';
import '../services/location_service.dart';
import '../theme.dart';
import 'package:dio/dio.dart';
import '../api/api_error.dart';

class BountyDetailScreen extends ConsumerStatefulWidget {
  const BountyDetailScreen({super.key});

  @override
  ConsumerState<BountyDetailScreen> createState() => _BountyDetailScreenState();
}

class _BountyDetailScreenState extends ConsumerState<BountyDetailScreen> {
  final LocationService _locationService = LocationService();
  
  late Map<String, dynamic> _bounty;
  Position? _currentPosition;
  double _distanceMeters = 9999.0;
  bool _canUnlock = false;
  bool _isClaiming = false;
  StreamSubscription<Position>? _positionStream;

  String? _couponCode;
  String? _couponText;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final args = ModalRoute.of(context)!.settings.arguments as Map<String, dynamic>;
    _bounty = args['bounty'];
    _currentPosition = args['currentPos'];
    _updateDistance();
    _startRadar();
  }

  @override
  void dispose() {
    _positionStream?.cancel();
    super.dispose();
  }

  void _startRadar() {
    _positionStream = _locationService.getLocationStream().listen((pos) {
      setState(() {
        _currentPosition = pos;
        _updateDistance();
      });
    });
  }

  void _updateDistance() {
    if (_currentPosition == null) return;
    
    _distanceMeters = _locationService.distanceBetween(
      _currentPosition!.latitude, 
      _currentPosition!.longitude, 
      _bounty['target_lat'], 
      _bounty['target_lng']
    );

    _canUnlock = _distanceMeters <= _bounty['radius_m'];
  }

  Future<void> _handleClaim() async {
    if (_bounty['target_score'] > 0) {
      // Needs a defense feat
      await _promptForFeat();
    } else {
      // Proximity only
      await _submitClaim(0);
    }
  }

  Future<void> _promptForFeat() async {
    final scoreController = TextEditingController();
    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          title: const Text('Bounty Challenge', style: TextStyle(color: AppTheme.primary)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Perform ${_bounty['target_score']} ${_bounty['activity_type']}!'),
              const SizedBox(height: 16),
              TextField(
                controller: scoreController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Score completed'),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel', style: TextStyle(color: AppTheme.error)),
            ),
            ElevatedButton(
              onPressed: () {
                Navigator.pop(context);
                _submitClaim(int.tryParse(scoreController.text) ?? 0);
              },
              child: const Text('SUBMIT'),
            ),
          ],
        );
      }
    );
  }

  Future<void> _submitClaim(int score) async {
    setState(() => _isClaiming = true);
    final userProfile = ref.read(authProvider);

    try {
      final response = await ref.read(apiClientProvider).completeBounty(
        _bounty['id'],
        {
          'user_id': userProfile!.id,
          'user_lat': _currentPosition!.latitude,
          'user_lng': _currentPosition!.longitude,
          'score': score,
          'device_timestamp': DateTime.now().toUtc().toIso8601String(),
        }
      );

      setState(() {
        if (response['coupon_code'] != null) {
          _couponCode = response['coupon_code'];
          _couponText = response['coupon_text'];
        } else {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(response['message']),
            backgroundColor: Colors.green,
          ));
          Navigator.pop(context); // Go back if it's just a normal claim
        }
      });
      
      // Refresh user profile in background to update XP/Crystals
      ref.read(authProvider.notifier).build(); 
      
    } on DioException catch (e) {
      if (mounted) {
        if (e.response?.statusCode == 409) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('You have already claimed this activity proof!'),
            backgroundColor: AppTheme.error,
          ));
        } else {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text('Failed: ${ApiError.getMessage(e)}'),
            backgroundColor: AppTheme.error,
          ));
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Claim failed: ${ApiError.getMessage(e)}'),
          backgroundColor: AppTheme.error,
        ));
      }
    } finally {
      if (mounted) setState(() => _isClaiming = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_bounty['title'])),
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Card(
              color: AppTheme.surface,
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  children: [
                    Icon(
                      _bounty['bounty_type'] == 'merchant_chest' ? Icons.storefront : Icons.stars,
                      size: 64,
                      color: AppTheme.primary,
                    ),
                    const SizedBox(height: 16),
                    Text(_bounty['description'], style: const TextStyle(fontSize: 16), textAlign: TextAlign.center),
                    const SizedBox(height: 16),
                    Text('Rewards: ${_bounty['xp_reward']} XP • ${_bounty['crystal_reward']} Crystals', style: const TextStyle(color: AppTheme.secondary, fontWeight: FontWeight.bold)),
                    if (_bounty['has_coupon'])
                      const Text('Contains a special merchant coupon!', style: TextStyle(color: Colors.amber, fontStyle: FontStyle.italic)),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 32),
            
            if (_couponCode != null) ...[
              // Coupon Reveal UI
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: Colors.amber.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: Colors.amber, width: 2),
                ),
                child: Column(
                  children: [
                    const Text('MERCHANT COUPON UNLOCKED!', style: TextStyle(color: Colors.amber, fontWeight: FontWeight.bold, fontSize: 18)),
                    const SizedBox(height: 16),
                    Text(_couponText ?? '', style: const TextStyle(fontSize: 16), textAlign: TextAlign.center),
                    const SizedBox(height: 16),
                    SelectableText(
                      _couponCode!,
                      style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold, letterSpacing: 4),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ] else ...[
              // Radar UI
              const Text('PROXIMITY RADAR', style: TextStyle(color: AppTheme.secondary, fontWeight: FontWeight.bold), textAlign: TextAlign.center),
              const SizedBox(height: 16),
              Stack(
                alignment: Alignment.center,
                children: [
                  SizedBox(
                    width: 150,
                    height: 150,
                    child: CircularProgressIndicator(
                      value: _canUnlock ? 1.0 : (_bounty['radius_m'] / _distanceMeters).clamp(0.0, 1.0),
                      strokeWidth: 10,
                      backgroundColor: AppTheme.surface,
                      color: _canUnlock ? Colors.green : AppTheme.primary,
                    ),
                  ),
                  Text(
                    '${_distanceMeters.toStringAsFixed(0)}m\naway',
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Text(
                _canUnlock ? 'IN RANGE' : 'Target radius: ${_bounty['radius_m']}m',
                textAlign: TextAlign.center,
                style: TextStyle(color: _canUnlock ? Colors.green : AppTheme.textSecondary, fontWeight: FontWeight.bold),
              ),
              const Spacer(),
              
              _isClaiming
                ? const Center(child: CircularProgressIndicator())
                : ElevatedButton.icon(
                    onPressed: _canUnlock ? _handleClaim : null,
                    icon: const Icon(Icons.lock_open),
                    label: const Text('UNLOCK CHEST'),
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 20),
                      backgroundColor: _canUnlock ? Colors.green : AppTheme.surface,
                    ),
                  ),
            ]
          ],
        ),
      ),
    );
  }
}
