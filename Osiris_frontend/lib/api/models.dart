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
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      id: json['id'],
      email: json['email'],
      bmi: json['bmi']?.toDouble() ?? 0.0,
      avatarClass: json['avatar_class'],
      xp: json['xp'],
      rank: json['rank'],
      title: json['title'],
      cumulativeArea: json['cumulative_area']?.toDouble() ?? 0.0,
      lastActivityDate: DateTime.parse(json['last_activity_date']),
      streak: json['streak'],
      manaCrystals: json['mana_crystals'],
      strStat: json['str_stat'],
      agiStat: json['agi_stat'],
      endStat: json['end_stat'],
      conStat: json['con_stat'],
    );
  }
}
