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

  UserProfile({
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
      id: json['id'],
      email: json['email'],
      bmi: json['bmi']?.toDouble() ?? 0.0,
      avatarClass: json['avatar_class'] ?? 'Admin',
      xp: json['xp'] ?? 0,
      rank: json['rank'] ?? 'Unranked',
      title: json['title'] ?? 'Portal Access',
      cumulativeArea: json['cumulative_area']?.toDouble() ?? 0.0,
      lastActivityDate: json['last_activity_date'] != null 
          ? DateTime.parse(json['last_activity_date']) 
          : DateTime.now(),
      streak: json['streak'] ?? 0,
      manaCrystals: json['mana_crystals'] ?? 0,
      strStat: json['str_stat'] ?? 0,
      agiStat: json['agi_stat'] ?? 0,
      endStat: json['end_stat'] ?? 0,
      conStat: json['con_stat'] ?? 0,
      role: json['role'] ?? 'player',
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

  PartyRoleResponse({
    required this.role,
    required this.leadingStat,
    required this.strStat,
    required this.agiStat,
    required this.endStat,
    required this.conStat,
  });

  factory PartyRoleResponse.fromJson(Map<String, dynamic> json) {
    return PartyRoleResponse(
      role: json['role'],
      leadingStat: json['leading_stat'],
      strStat: json['str_stat'],
      agiStat: json['agi_stat'],
      endStat: json['end_stat'],
      conStat: json['con_stat'],
    );
  }
}
