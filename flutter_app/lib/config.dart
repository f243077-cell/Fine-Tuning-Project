/// Base URLs come from --dart-define at run time (see flutter_app/README.md).
///
/// GUARD_API_KEY is the key of your own local guard-api, passed in at run time for the playground.
/// It is never committed, and the app holds no LLM provider key of any kind.
class AppConfig {
  const AppConfig({required this.guardUrl, required this.demoUrl, required this.guardApiKey});

  /// A URL starting with '/' (the hosted demo: GUARD_URL=/guard, DEMO_URL=/demo) is resolved against the page,
  /// so the app calls its own origin and the deploy proxy adds the key on the server (no key in the build).
  factory AppConfig.fromEnvironment() => AppConfig(
        guardUrl: _absolute(const String.fromEnvironment('GUARD_URL', defaultValue: 'http://localhost:8001')),
        demoUrl: _absolute(const String.fromEnvironment('DEMO_URL', defaultValue: 'http://localhost:8002')),
        guardApiKey: const String.fromEnvironment('GUARD_API_KEY'),
      );

  static String _absolute(String url) =>
      url.startsWith('/') ? Uri.base.resolve(url).toString().replaceFirst(RegExp(r'/$'), '') : url;

  final String guardUrl;
  final String demoUrl;
  final String guardApiKey;
}
