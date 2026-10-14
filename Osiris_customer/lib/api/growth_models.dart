// Models for the growth release: today's quest, profile, sharing, communities,
// rankings, seasons, and safety settings.

double _d(dynamic v) => (v as num?)?.toDouble() ?? 0.0;

const goalLabels = {
  'fitness': 'Get fitter',
  'running': 'Run more',
  'consistency': 'Build a habit',
  'competition': 'Compete',
};

const goalDescriptions = {
  'fitness': 'Short, doable quests that build up week by week.',
  'running': 'Quests sized to your recent runs.',
  'consistency': 'Easy quests that make three active days a week stick.',
  'competition': 'Slightly harder quests, plus challenges and rankings.',
};

const communityKindLabels = {
  'running_club': 'Running club',
  'gym': 'Gym',
  'university': 'University group',
  'trainer': 'Personal trainer',
  'race': 'Race',
  'cafe': 'Cafe',
  'corporate': 'Workplace',
  'other': 'Community',
};

String kmLabel(double metres) {
  final km = metres / 1000;
  return km >= 10 ? '${km.toStringAsFixed(0)} km' : '${km.toStringAsFixed(1)} km';
}

class PlayerProfileV2 {
  final int userId;
  final String displayName;
  final String goal;
  final String identity;
  final bool publicProfile;
  final bool locationConsent;
  final bool onboardingCompleted;
  final String referralCode;
  final String? city;
  final bool leaderboardOptIn;

  const PlayerProfileV2({
    required this.userId,
    required this.displayName,
    required this.goal,
    required this.identity,
    required this.publicProfile,
    required this.locationConsent,
    required this.onboardingCompleted,
    required this.referralCode,
    required this.city,
    required this.leaderboardOptIn,
  });

  factory PlayerProfileV2.fromJson(Map<String, dynamic> j) => PlayerProfileV2(
        userId: j['user_id'] as int,
        displayName: j['display_name'] as String? ?? '',
        goal: j['goal'] as String? ?? 'fitness',
        identity: j['identity'] as String? ?? 'athlete',
        publicProfile: j['public_profile'] as bool? ?? false,
        locationConsent: j['location_consent'] as bool? ?? false,
        onboardingCompleted: j['onboarding_completed'] as bool? ?? false,
        referralCode: j['referral_code'] as String? ?? '',
        city: j['city'] as String?,
        leaderboardOptIn: j['leaderboard_opt_in'] as bool? ?? false,
      );
}

class Quest {
  final String key;
  final String kind;
  final String title;
  final String description;
  final int targetM;
  final int xp;
  final bool optional;
  final double progressM;
  final bool completed;
  final bool rewarded;

  const Quest({
    required this.key,
    required this.kind,
    required this.title,
    required this.description,
    required this.targetM,
    required this.xp,
    required this.optional,
    required this.progressM,
    required this.completed,
    required this.rewarded,
  });

  double get fraction => targetM <= 0 ? 0 : (progressM / targetM).clamp(0.0, 1.0);

  factory Quest.fromJson(Map<String, dynamic> j) => Quest(
        key: j['key'] as String,
        kind: j['kind'] as String,
        title: j['title'] as String,
        description: j['description'] as String? ?? '',
        targetM: j['target_m'] as int? ?? 0,
        xp: j['xp'] as int? ?? 0,
        optional: j['optional'] as bool? ?? false,
        progressM: _d(j['progress_m']),
        completed: j['completed'] as bool? ?? false,
        rewarded: j['rewarded'] as bool? ?? false,
      );
}

class WeeklyGoal {
  final int activeDaysTarget;
  final int activeDays;
  final double distanceM;
  final int xp;
  final bool completed;

  const WeeklyGoal({
    required this.activeDaysTarget,
    required this.activeDays,
    required this.distanceM,
    required this.xp,
    required this.completed,
  });

  factory WeeklyGoal.fromJson(Map<String, dynamic> j) => WeeklyGoal(
        activeDaysTarget: j['active_days_target'] as int? ?? 3,
        activeDays: j['active_days'] as int? ?? 0,
        distanceM: _d(j['distance_m']),
        xp: j['xp'] as int? ?? 0,
        completed: j['completed'] as bool? ?? false,
      );
}

class TodayData {
  final String tagline;
  final String displayName;
  final String identity;
  final String goal;
  final int xp;
  final String performanceRank;
  final Quest today;
  final Quest tomorrow;
  final WeeklyGoal week;
  final int streakWeeks;
  final Map<String, dynamic>? starterChallenge;
  final String safetyNote;
  final bool needsLocationConsent;

  const TodayData({
    required this.tagline,
    required this.displayName,
    required this.identity,
    required this.goal,
    required this.xp,
    required this.performanceRank,
    required this.today,
    required this.tomorrow,
    required this.week,
    required this.streakWeeks,
    required this.starterChallenge,
    required this.safetyNote,
    required this.needsLocationConsent,
  });

  factory TodayData.fromJson(Map<String, dynamic> j) => TodayData(
        tagline: j['tagline'] as String? ?? '',
        displayName: j['display_name'] as String? ?? '',
        identity: j['identity'] as String? ?? '',
        goal: j['goal'] as String? ?? 'fitness',
        xp: j['xp'] as int? ?? 0,
        performanceRank: j['performance_rank'] as String? ?? '',
        today: Quest.fromJson(j['today'] as Map<String, dynamic>),
        tomorrow: Quest.fromJson(j['tomorrow'] as Map<String, dynamic>),
        week: WeeklyGoal.fromJson(j['week'] as Map<String, dynamic>),
        streakWeeks: j['streak_weeks'] as int? ?? 0,
        starterChallenge: j['starter_challenge'] as Map<String, dynamic>?,
        safetyNote: j['safety_note'] as String? ?? '',
        needsLocationConsent: j['needs_location_consent'] as bool? ?? false,
      );
}

class ShareCardData {
  final String token;
  final String url;
  final String headline;
  final String shareText;

  const ShareCardData({required this.token, required this.url, required this.headline, required this.shareText});

  factory ShareCardData.fromJson(Map<String, dynamic> j) => ShareCardData(
        token: j['token'] as String,
        url: j['url'] as String,
        headline: j['headline'] as String? ?? '',
        shareText: j['share_text'] as String? ?? j['url'] as String,
      );
}

class TeamGoal {
  final double goalKm;
  final double progressKm;
  final bool completed;
  final int activeMembers;

  const TeamGoal({required this.goalKm, required this.progressKm, required this.completed, required this.activeMembers});

  double get fraction => goalKm <= 0 ? 0 : (progressKm / goalKm).clamp(0.0, 1.0);

  factory TeamGoal.fromJson(Map<String, dynamic> j) => TeamGoal(
        goalKm: _d(j['goal_km']),
        progressKm: _d(j['progress_km']),
        completed: j['completed'] as bool? ?? false,
        activeMembers: j['active_members'] as int? ?? 0,
      );
}

class Community {
  final String slug;
  final String name;
  final String kind;
  final String? description;
  final String? brandColor;
  final String? city;
  final String visibility;
  final bool verified;
  final String? perkText;
  final int memberCount;
  final String? myRole;
  final String? joinCode;
  final TeamGoal? teamGoal;

  const Community({
    required this.slug,
    required this.name,
    required this.kind,
    required this.description,
    required this.brandColor,
    required this.city,
    required this.visibility,
    required this.verified,
    required this.perkText,
    required this.memberCount,
    required this.myRole,
    required this.joinCode,
    required this.teamGoal,
  });

  bool get isMember => myRole != null;

  factory Community.fromJson(Map<String, dynamic> j) => Community(
        slug: j['slug'] as String,
        name: j['name'] as String,
        kind: j['kind'] as String? ?? 'other',
        description: j['description'] as String?,
        brandColor: j['brand_color'] as String?,
        city: j['city'] as String?,
        visibility: j['visibility'] as String? ?? 'public',
        verified: j['verified'] as bool? ?? false,
        perkText: j['perk_text'] as String?,
        memberCount: j['member_count'] as int? ?? 0,
        myRole: j['my_role'] as String?,
        joinCode: j['join_code'] as String?,
        teamGoal: j['team_goal'] == null ? null : TeamGoal.fromJson(j['team_goal'] as Map<String, dynamic>),
      );
}

class LeaderboardRow {
  final int rank;
  final String name;
  final int points;
  final int activeDays;
  final double distanceKm;
  final bool isMe;

  const LeaderboardRow({
    required this.rank,
    required this.name,
    required this.points,
    required this.activeDays,
    required this.distanceKm,
    required this.isMe,
  });

  factory LeaderboardRow.fromJson(Map<String, dynamic> j) => LeaderboardRow(
        rank: j['rank'] as int,
        name: j['name'] as String,
        points: j['points'] as int? ?? 0,
        activeDays: j['active_days'] as int? ?? 0,
        distanceKm: _d(j['distance_km']),
        isMe: j['is_me'] as bool? ?? false,
      );
}

class Leaderboard {
  final String title;
  final String scoring;
  final List<LeaderboardRow> rows;
  final LeaderboardRow? myRow;
  final int rankedPlayers;

  const Leaderboard({
    required this.title,
    required this.scoring,
    required this.rows,
    required this.myRow,
    required this.rankedPlayers,
  });

  factory Leaderboard.fromJson(Map<String, dynamic> j) => Leaderboard(
        title: j['title'] as String? ?? '',
        scoring: j['scoring'] as String? ?? '',
        rows: (j['rows'] as List<dynamic>? ?? [])
            .map((r) => LeaderboardRow.fromJson(r as Map<String, dynamic>))
            .toList(),
        myRow: j['my_row'] == null ? null : LeaderboardRow.fromJson(j['my_row'] as Map<String, dynamic>),
        rankedPlayers: j['ranked_players'] as int? ?? 0,
      );
}

class Season {
  final String slug;
  final String name;
  final String city;
  final String? description;
  final String status;
  final bool entered;
  final int participants;
  final DateTime endsAt;

  const Season({
    required this.slug,
    required this.name,
    required this.city,
    required this.description,
    required this.status,
    required this.entered,
    required this.participants,
    required this.endsAt,
  });

  factory Season.fromJson(Map<String, dynamic> j) => Season(
        slug: j['slug'] as String,
        name: j['name'] as String,
        city: j['city'] as String? ?? '',
        description: j['description'] as String?,
        status: j['status'] as String? ?? 'live',
        entered: j['entered'] as bool? ?? false,
        participants: j['participants'] as int? ?? 0,
        endsAt: DateTime.parse(j['ends_at'] as String),
      );
}

class ReferralSummary {
  final String code;
  final String url;
  final int pending;
  final int rewarded;
  final List<String> rules;

  const ReferralSummary({
    required this.code,
    required this.url,
    required this.pending,
    required this.rewarded,
    required this.rules,
  });

  factory ReferralSummary.fromJson(Map<String, dynamic> j) => ReferralSummary(
        code: j['referral_code'] as String,
        url: j['url'] as String,
        pending: j['pending'] as int? ?? 0,
        rewarded: j['rewarded'] as int? ?? 0,
        rules: (j['rules'] as List<dynamic>? ?? []).cast<String>(),
      );
}
