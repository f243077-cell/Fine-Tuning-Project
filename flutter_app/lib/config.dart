/// Base URLs come from --dart-define at run time (see flutter_app/README.md).
///
/// GUARD_API_KEY is the key of your own local guard-api, passed in at run time for the playground.
/// It is never committed, and the app holds no LLM provider key of any kind.
class AppConfig {
  const AppConfig({required this.guardUrl, required this.demoUrl, required this.guardApiKey});

  factory AppConfig.fromEnvironment() => const AppConfig(
        guardUrl: String.fromEnvironment('GUARD_URL', defaultValue: 'http://localhost:8001'),
        demoUrl: String.fromEnvironment('DEMO_URL', defaultValue: 'http://localhost:8002'),
        guardApiKey: String.fromEnvironment('GUARD_API_KEY'),
      );

  final String guardUrl;
  final String demoUrl;
  final String guardApiKey;
}
