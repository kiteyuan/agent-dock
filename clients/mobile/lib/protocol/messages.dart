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
  return encode(Msg.deviceHello, payload);
}

String userMessage({
  required String sessionId,
  required String text,
  String? agentId,
  String? ttsId,
  String? ttsModel,
  List<Map<String, String>>? images,
}) {
  final payload = <String, dynamic>{
    'session_id': sessionId,
    'text': text,
  };
  if (agentId != null) payload['agent_id'] = agentId;
  if (ttsId != null) payload['tts_id'] = ttsId;
  if (ttsModel != null) payload['tts_model'] = ttsModel;
  if (images != null && images.isNotEmpty) {
    payload['images'] = images;
  }
  return encode(Msg.userMessage, payload);
}

String audioStart(String sessionId) =>
    encode(Msg.audioStart, {'session_id': sessionId});

String audioEnd(String sessionId) =>
    encode(Msg.audioEnd, {'session_id': sessionId});

String sessionCancel(String sessionId) =>
    encode(Msg.sessionCancel, {'session_id': sessionId});

String sessionReset([String? sessionId]) {
  final payload = <String, dynamic>{};
  if (sessionId != null && sessionId.isNotEmpty) {
    payload['session_id'] = sessionId;
  }
  return encode(Msg.sessionReset, payload);
}

String ttsList() => encode(Msg.ttsList);

String petsList() => encode(Msg.petsList);

String ttsSelect(String sessionId, String ttsId, {String? model}) {
  final payload = <String, dynamic>{
    'session_id': sessionId,
    'tts_id': ttsId,
  };
  if (model != null && model.isNotEmpty) payload['model'] = model;
  return encode(Msg.ttsSelect, payload);
}

String ping([String? pingId]) =>
    encode(Msg.ping, {'ping_id': pingId ?? _id().substring(0, 8)});
