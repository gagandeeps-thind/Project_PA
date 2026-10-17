import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osiris_customer/providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('fresh install drops credentials left in the keychain', () async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({'auth_token': 'old', 'user_id': '7'});
    final prefs = await SharedPreferences.getInstance();
    const storage = FlutterSecureStorage();

    await dropOrphanedCredentials(prefs, storage);

    expect(await storage.read(key: 'auth_token'), isNull);
    expect(await storage.read(key: 'user_id'), isNull);
    expect(prefs.getBool('install_seen'), isTrue);
  });

  test('a known install keeps its session', () async {
    SharedPreferences.setMockInitialValues({'install_seen': true});
    FlutterSecureStorage.setMockInitialValues({'auth_token': 'tok', 'user_id': '7'});
    final prefs = await SharedPreferences.getInstance();
    const storage = FlutterSecureStorage();

    await dropOrphanedCredentials(prefs, storage);

    expect(await storage.read(key: 'auth_token'), 'tok');
    expect(await storage.read(key: 'user_id'), '7');
  });
}
