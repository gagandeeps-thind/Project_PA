/// Merchant profile returned by GET /api/v1/merchants/{id}
class MerchantProfile {
  final int id;
  final String name;
  final String email;
  final String businessType;
  final bool isActive;
  final String paymentStatus;
  final String? paymentProviderId;
  final int pilotFeeCents;
  final DateTime? lastPaymentAt;
  final String role;

  MerchantProfile({
    required this.id,
    required this.name,
    required this.email,
    required this.businessType,
    required this.isActive,
    required this.paymentStatus,
    this.paymentProviderId,
    required this.pilotFeeCents,
    this.lastPaymentAt,
    required this.role,
  });

  factory MerchantProfile.fromJson(Map<String, dynamic> json) {
    return MerchantProfile(
      id: json['id'] ?? json['merchant_id'] ?? 0,
      name: json['name'] ?? json['business_name'] ?? 'Unknown',
      email: json['email'] ?? '',
      businessType: json['business_type'] ?? 'general',
      isActive: json['is_active'] ?? false,
      paymentStatus: json['payment_status'] ?? 'pending',
      paymentProviderId: json['payment_provider_id'],
      pilotFeeCents: json['pilot_fee_cents'] ?? 4999,
      lastPaymentAt: json['last_payment_at'] != null
          ? DateTime.tryParse(json['last_payment_at'])
          : null,
      role: json['role'] ?? 'merchant',
    );
  }
}

/// A bounty owned by the merchant.
class MerchantBounty {
  final int id;
  final String title;
  final String description;
  final String bountyType;
  final int completionsRemaining;
  final int completionsCount;
  final int couponsIssued;
  final double radiusM;
  final double targetLat;
  final double targetLng;
  final String? couponText;
  final bool isActive;

  MerchantBounty({
    required this.id,
    required this.title,
    required this.description,
    required this.bountyType,
    required this.completionsRemaining,
    required this.completionsCount,
    required this.couponsIssued,
    required this.radiusM,
    required this.targetLat,
    required this.targetLng,
    this.couponText,
    required this.isActive,
  });

  factory MerchantBounty.fromJson(Map<String, dynamic> json) {
    return MerchantBounty(
      id: json['id'] ?? 0,
      title: json['title'] ?? 'Untitled',
      description: json['description'] ?? '',
      bountyType: json['bounty_type'] ?? 'merchant_chest',
      completionsRemaining: json['completions_remaining'] ?? 0,
      completionsCount: json['completions_count'] ?? 0,
      couponsIssued: json['coupons_issued'] ?? 0,
      radiusM: (json['radius_m'] ?? 30.0).toDouble(),
      targetLat: (json['target_lat'] ?? 0.0).toDouble(),
      targetLng: (json['target_lng'] ?? 0.0).toDouble(),
      couponText: json['coupon_text'],
      isActive: json['is_active'] ?? true,
    );
  }
}

/// Payment intent returned by POST /api/v1/merchants/{id}/payments/intent
class PaymentIntent {
  final String providerPaymentId;
  final int amountCents;
  final String nextAction;

  PaymentIntent({
    required this.providerPaymentId,
    required this.amountCents,
    required this.nextAction,
  });

  factory PaymentIntent.fromJson(Map<String, dynamic> json) {
    return PaymentIntent(
      providerPaymentId: json['provider_payment_id'] ?? '',
      amountCents: json['amount_cents'] ?? 0,
      nextAction: json['next_action'] ?? 'unknown',
    );
  }
}
