import 'dart:convert';

import 'exercise_catalog.dart';
import 'exercise_store.dart';

/// Where the rep engine's catalog comes from: the server copy cached in SQLite when there is
/// one, otherwise the copy bundled with the app. [refresh] fetches the server copy in the
/// background so threshold changes reach the phone without an app release.
class CatalogRepository {
  final ExerciseStore store;
  final Future<String> Function() loadBundled;
  final Future<Map<String, dynamic>> Function() fetch;

  CatalogRepository({required this.store, required this.loadBundled, required this.fetch});

  Future<ExerciseCatalog> load() async {
    final cached = await store.cachedCatalogJson();
    if (cached != null) {
      try {
        return ExerciseCatalog.parse(cached);
      } on Object {
        // A cache written by an incompatible app version; fall back to the bundled copy.
      }
    }
    return ExerciseCatalog.parse(await loadBundled());
  }

  /// Returns the fresh catalog, or null when offline or the payload does not parse.
  Future<ExerciseCatalog?> refresh() async {
    try {
      final data = await fetch();
      final catalog = ExerciseCatalog.fromJson(data);
      await store.cacheCatalog(catalog.rulesVersion, jsonEncode(data));
      return catalog;
    } on Object {
      return null;
    }
  }
}
