import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import 'session/device_session.dart';
import 'ui/home_page.dart';
import 'ui/theme.dart';

Future<String> _stableDeviceId() async {
  final p = await SharedPreferences.getInstance();
  const key = 'device_id';
  final existing = p.getString(key);
  if (existing != null && existing.isNotEmpty) return existing;
  final id = 'mobile-${const Uuid().v4().replaceAll('-', '').substring(0, 12)}';
  await p.setString(key, id);
  return id;
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final deviceId = await _stableDeviceId();
  runApp(AgentDockApp(deviceId: deviceId));
}

class AgentDockApp extends StatefulWidget {
  const AgentDockApp({super.key, required this.deviceId});

  final String deviceId;

  @override
  State<AgentDockApp> createState() => _AgentDockAppState();
}

class _AgentDockAppState extends State<AgentDockApp> with WidgetsBindingObserver {
  late final DeviceSession _session;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _session = DeviceSession(deviceId: widget.deviceId);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _session.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_session.onAppResumed());
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AgentDock',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: WebUiTheme.bg0,
        colorScheme: ColorScheme.fromSeed(
          seedColor: WebUiTheme.accent,
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: HomePage(session: _session),
    );
  }
}
