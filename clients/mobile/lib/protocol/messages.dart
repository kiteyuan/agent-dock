/// Device Protocol wire helpers (align with runtime/protocol/device.py).
library;

import 'dart:convert';

import 'package:uuid/uuid.dart';

const protocolVersion = '1.0';

String _id() => const Uuid().v4().replaceAll('-', '').substring(0, 12);

Map<String, dynamic> envelope(String type, [Map<String, dynamic>? payload]) {
  return {
    'type': type,
    'id': _id(),
    'ts': DateTime.now().millisecondsSinceEpoch / 1000.0,
    'payload': payload ?? <String, dynamic>{},
  };
}

String encode(String type, [Map<String, dynamic>? payload]) {
  return jsonEncode(envelope(type, payload));
}

Map<String, dynamic>? decodeJson(String raw) {
  try {
    final obj = jsonDecode(raw);
    if (obj is Map<String, dynamic>) return obj;
    if (obj is Map) return Map<String, dynamic>.from(obj);
  } catch (_) {}
  return null;
}

String deviceHello({
  required String deviceId,
  String deviceType = 'mobile',
  String? token,
  String? ttsId,
}) {
  final payload = <String, dynamic>{
    'device_id': deviceId,
    'device_type': deviceType,
    'protocol_version': protocolVersion,
  };
  if (token != null && token.isNotEmpty) payload['token'] = token;
  if (ttsId != null && ttsId.isNotEmpty) payload['tts_id'] = ttsId;
  return encode('device.hello', payload);
}

String userMessage({
  required String sessionId,
  required String text,
  String? agentId,
  String? ttsId,
  String? ttsModel,
}) {
  final payload = <String, dynamic>{
    'session_id': sessionId,
    'text': text,
  };
  if (agentId != null) payload['agent_id'] = agentId;
  if (ttsId != null) payload['tts_id'] = ttsId;
  if (ttsModel != null) payload['tts_model'] = ttsModel;
  return encode('user.message', payload);
}

String audioStart(String sessionId) =>
    encode('audio.start', {'session_id': sessionId});

String audioEnd(String sessionId) =>
    encode('audio.end', {'session_id': sessionId});

String sessionCancel(String sessionId) =>
    encode('session.cancel', {'session_id': sessionId});

String sessionReset([String? sessionId]) {
  final payload = <String, dynamic>{};
  if (sessionId != null && sessionId.isNotEmpty) {
    payload['session_id'] = sessionId;
  }
  return encode('session.reset', payload);
}

String ttsList() => encode('tts.list');

String petsList() => encode('pets.list');

String ttsSelect(String sessionId, String ttsId, {String? model}) {
  final payload = <String, dynamic>{
    'session_id': sessionId,
    'tts_id': ttsId,
  };
  if (model != null && model.isNotEmpty) payload['model'] = model;
  return encode('tts.select', payload);
}

String ping([String? pingId]) =>
    encode('device.ping', {'ping_id': pingId ?? _id().substring(0, 8)});
