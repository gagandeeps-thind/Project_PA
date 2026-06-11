/// Domain models for the Osiris Customer app.

class UserProfile {
  final int id;
  final String email;
  final double bmi;
  final String avatarClass;
  final int xp;
  final String rank;
  final String title;
  final double cumulativeArea;
  final DateTime lastActivityDate;
  final int streak;
  final int manaCrystals;
  final int strStat;
  final int agiStat;
  final int endStat;
  final int conStat;
  final String role;

  const UserProfile({
    required this.id,
    required this.email,
    required this.bmi,
    required this.avatarClass,
    required this.xp,
    required this.rank,
    required this.title,
    required this.cumulativeArea,
    required this.lastActivityDate,
    required this.streak,
    required this.manaCrystals,
    required this.strStat,
    required this.agiStat,
    required this.endStat,
    required this.conStat,
    required this.role,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      id: json['id'] as int,
      email: json['email'] as String? ?? '',
      bmi: (json['bmi'] as num?)?.toDouble() ?? 0.0,
      avatarClass: json['avatar_class'] as String? ?? 'warrior',
      xp: json['xp'] as int? ?? 0,
      rank: json['rank'] as String? ?? 'Unranked',
      title: json['title'] as String? ?? 'Novice',
      cumulativeArea:
          (json['cumulative_area'] as num?)?.toDouble() ?? 0.0,
      lastActivityDate: json['last_activity_date'] != null
          ? DateTime.parse(json['last_activity_date'] as String)
          : DateTime.now(),
      streak: json['streak'] as int? ?? 0,
      manaCrystals: json['mana_crystals'] as int? ?? 0,
      strStat: json['str_stat'] as int? ?? 0,
      agiStat: json['agi_stat'] as int? ?? 0,
      endStat: json['end_stat'] as int? ?? 0,
      conStat: json['con_stat'] as int? ?? 0,
      role: json['role'] as String? ?? 'player',
    );
  }
}

class PartyRoleResponse {
  final String role;
  final String leadingStat;
  final int strStat;
  final int agiStat;
  final int endStat;
  final int conStat;

  const PartyRoleResponse({
    required this.role,
    required this.leadingStat,
    required this.strStat,
    required this.agiStat,
    required this.endStat,
    required this.conStat,
  });

  factory PartyRoleResponse.fromJson(Map<String, dynamic> json) {
    return PartyRoleResponse(
      role: json['role'] as String? ?? 'DPS',
      leadingStat: json['leading_stat'] as String? ?? 'str',
      strStat: json['str_stat'] as int? ?? 0,
      agiStat: json['agi_stat'] as int? ?? 0,
      endStat: json['end_stat'] as int? ?? 0,
      conStat: json['con_stat'] as int? ?? 0,
    );
  }
}
