// Keeps the Android and iOS builds describing the same app. These read the checked-in
// platform files, so a change on one side without the other fails `flutter test`.
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osiris_customer/api/api_client.dart';

String _read(String path) => File(path).readAsStringSync();

String _plistString(String plist, String key) {
  final m = RegExp('<key>$key</key>\\s*<string>([^<]*)</string>').firstMatch(plist);
  expect(m, isNotNull, reason: 'Info.plist is missing $key');
  return m!.group(1)!;
}

void main() {
  final manifest = _read('android/app/src/main/AndroidManifest.xml');
  final plist = _read('ios/Runner/Info.plist');
  final pbx = _read('ios/Runner.xcodeproj/project.pbxproj');
  final gradle = _read('android/app/build.gradle.kts');

  test('both stores show the same app name', () {
    final android = RegExp(r'android:label="([^"]*)"').firstMatch(manifest)!.group(1);
    expect(_plistString(plist, 'CFBundleDisplayName'), android);
  });

  test('both platforms take version and build number from pubspec', () {
    expect(_plistString(plist, 'CFBundleShortVersionString'), r'$(FLUTTER_BUILD_NAME)');
    expect(_plistString(plist, 'CFBundleVersion'), r'$(FLUTTER_BUILD_NUMBER)');
    expect(gradle, contains('versionCode = flutter.versionCode'));
    expect(gradle, contains('versionName = flutter.versionName'));
  });

  test('application ids are the same string up to platform rules', () {
    String norm(String s) => s.replaceAll('_', '').toLowerCase();
    final android = RegExp(r'applicationId = "([^"]+)"').firstMatch(gradle)!.group(1)!;
    final ios = RegExp(r'PRODUCT_BUNDLE_IDENTIFIER = ([\w.]+);(?!.*RunnerTests)')
        .allMatches(pbx)
        .map((m) => m.group(1)!)
        .where((id) => !id.endsWith('RunnerTests'))
        .toSet();
    expect(ios, hasLength(1), reason: 'Runner must use one bundle id in every configuration');
    expect(norm(ios.single), norm(android));
  });

  test('location: same capability and rationale on both platforms', () {
    expect(manifest, contains('android.permission.ACCESS_FINE_LOCATION'));
    expect(manifest, contains('android.permission.FOREGROUND_SERVICE_LOCATION'));
    expect(manifest, isNot(contains('<uses-permission android:name="android.permission.ACCESS_BACKGROUND_LOCATION"')));
    expect(plist, contains('NSLocationWhenInUseUsageDescription'));
    expect(plist, isNot(contains('NSLocationAlwaysAndWhenInUseUsageDescription')));
    expect(RegExp(r'UIBackgroundModes</key>\s*<array>\s*<string>location</string>\s*</array>')
        .hasMatch(plist), isTrue);
  });

  test('camera: permission and purpose string on both platforms', () {
    expect(manifest, contains('android.permission.CAMERA'));
    final purpose = _plistString(plist, 'NSCameraUsageDescription');
    expect(purpose, contains('no video or photos are saved or uploaded'));
  });

  test('neither platform opts in to cleartext traffic', () {
    expect(manifest, isNot(contains('usesCleartextTraffic="true"')));
    expect(plist, isNot(contains('NSAllowsArbitraryLoads')));
  });

  group('API base URL', () {
    test('debug default reaches the dev machine from each emulator', () {
      expect(resolveApiBaseUrl(configured: '', platform: TargetPlatform.android, release: false),
          'http://10.0.2.2:8000');
      expect(resolveApiBaseUrl(configured: '', platform: TargetPlatform.iOS, release: false),
          'http://127.0.0.1:8000');
    });

    test('an explicit value wins on both platforms', () {
      for (final p in [TargetPlatform.android, TargetPlatform.iOS]) {
        expect(resolveApiBaseUrl(configured: 'https://api.example.org', platform: p, release: true),
            'https://api.example.org');
      }
    });

    test('release refuses a missing or cleartext origin on both platforms', () {
      for (final p in [TargetPlatform.android, TargetPlatform.iOS]) {
        for (final bad in ['', 'http://10.0.2.2:8000', 'http://api.example.org']) {
          expect(() => resolveApiBaseUrl(configured: bad, platform: p, release: true),
              throwsStateError);
        }
      }
    });
  });
}
