import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../theme.dart';
import '../providers.dart';
import '../api/api_error.dart';

/// MVP coupon scanner — manual text input for coupon codes.
/// Camera-based QR scanning is Phase 2.
class CouponScannerScreen extends ConsumerStatefulWidget {
  const CouponScannerScreen({super.key});

  @override
  ConsumerState<CouponScannerScreen> createState() =>
      _CouponScannerScreenState();
}

class _CouponScannerScreenState extends ConsumerState<CouponScannerScreen> {
  final _codeController = TextEditingController();
  bool _isRedeeming = false;
  _RedemptionResult? _result;

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _handleRedeem() async {
    final code = _codeController.text.trim();
    if (code.isEmpty) {
      setState(() => _result = _RedemptionResult(
            success: false,
            message: 'Please enter a coupon code.',
          ));
      return;
    }

    setState(() {
      _isRedeeming = true;
      _result = null;
    });

    try {
      final client = ref.read(apiClientProvider);
      final data = await client.redeemCoupon(code);
      setState(() => _result = _RedemptionResult(
            success: true,
            message: data['message'] ?? 'Coupon redeemed successfully!',
          ));
      _codeController.clear();
    } catch (e) {
      setState(() => _result = _RedemptionResult(
            success: false,
            message: ApiError.getMessage(e),
          ));
    } finally {
      if (mounted) setState(() => _isRedeeming = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('REDEEM COUPON'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SizedBox(height: 20),

            // ── Scanner Icon ──
            Center(
              child: Container(
                width: 100,
                height: 100,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: MerchantTheme.primary.withAlpha(15),
                  border: Border.all(
                      color: MerchantTheme.primary.withAlpha(60), width: 2),
                ),
                child: const Icon(
                  Icons.qr_code_scanner_rounded,
                  size: 48,
                  color: MerchantTheme.primary,
                ),
              ),
            ),
            const SizedBox(height: 24),

            // ── Instructions ──
            const Text(
              'Enter Coupon Code',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w700,
                color: MerchantTheme.textPrimary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            const Text(
              'Type or paste the customer\'s coupon code below.\nQR camera scanning coming in Phase 2.',
              style: TextStyle(
                fontSize: 13,
                color: MerchantTheme.textSecondary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 28),

            // ── Code Input ──
            Container(
              decoration: MerchantTheme.glassCard,
              padding: const EdgeInsets.all(20),
              child: Column(
                children: [
                  TextFormField(
                    controller: _codeController,
                    textCapitalization: TextCapitalization.characters,
                    style: const TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                      color: MerchantTheme.primary,
                      letterSpacing: 4,
                    ),
                    textAlign: TextAlign.center,
                    decoration: InputDecoration(
                      hintText: 'XXXX-XXXX',
                      hintStyle: TextStyle(
                        color: MerchantTheme.textSecondary.withAlpha(100),
                        fontSize: 22,
                        letterSpacing: 4,
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide:
                            const BorderSide(color: MerchantTheme.divider),
                      ),
                    ),
                    onFieldSubmitted: (_) => _handleRedeem(),
                  ),
                  const SizedBox(height: 20),
                  SizedBox(
                    width: double.infinity,
                    height: 52,
                    child: ElevatedButton(
                      onPressed: _isRedeeming ? null : _handleRedeem,
                      child: _isRedeeming
                          ? const SizedBox(
                              width: 22,
                              height: 22,
                              child: CircularProgressIndicator(
                                strokeWidth: 2.5,
                                color: MerchantTheme.background,
                              ),
                            )
                          : const Text('REDEEM'),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),

            // ── Result Feedback ──
            if (_result != null)
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: _result!.success
                      ? MerchantTheme.success.withAlpha(15)
                      : MerchantTheme.error.withAlpha(15),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: _result!.success
                        ? MerchantTheme.success.withAlpha(80)
                        : MerchantTheme.error.withAlpha(80),
                  ),
                ),
                child: Row(
                  children: [
                    Icon(
                      _result!.success
                          ? Icons.check_circle_rounded
                          : Icons.error_outline,
                      color: _result!.success
                          ? MerchantTheme.success
                          : MerchantTheme.error,
                      size: 24,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        _result!.message,
                        style: TextStyle(
                          color: _result!.success
                              ? MerchantTheme.success
                              : MerchantTheme.error,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _RedemptionResult {
  final bool success;
  final String message;
  _RedemptionResult({required this.success, required this.message});
}
