import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../api/growth_models.dart';
import '../providers.dart';
import '../theme.dart';

/// Sharing without a platform share-sheet dependency: the link and text are copied to the
/// clipboard, ready to paste into any chat. Swapping in a native share sheet later only
/// needs a change here.
class ShareHelper {
  static Future<void> copy(BuildContext context, WidgetRef ref, String text, {String kind = 'link'}) async {
    await Clipboard.setData(ClipboardData(text: text));
    ref.read(apiClientProvider).trackEvent('share_completed', properties: {'kind': kind});
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
      content: Text('Link copied. Paste it into a message to share.'),
      backgroundColor: OsirisTheme.success,
    ));
  }

  /// Create (or reuse) the share card for an achievement, then copy it.
  static Future<void> shareAchievement(BuildContext context, WidgetRef ref, String kind, int entityId) async {
    try {
      final card = ShareCardData.fromJson(await ref.read(apiClientProvider).createShareCard(kind, entityId));
      if (!context.mounted) return;
      await copy(context, ref, card.shareText, kind: kind);
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(ApiError.getMessage(e)), backgroundColor: OsirisTheme.error),
      );
    }
  }

  /// Invite a friend to a challenge: the link carries your referral.
  static Future<void> inviteToChallenge(BuildContext context, WidgetRef ref, int challengeId) async {
    try {
      final data = await ref.read(apiClientProvider).createChallengeInvite(challengeId);
      if (!context.mounted) return;
      await copy(context, ref, data['share_text'] as String, kind: 'challenge_invite');
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(ApiError.getMessage(e)), backgroundColor: OsirisTheme.error),
      );
    }
  }
}
