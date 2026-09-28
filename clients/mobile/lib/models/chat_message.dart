enum ChatRole { user, assistant }

class ChatMessage {
  ChatMessage({required this.id, required this.role, required this.text});

  final String id;
  final ChatRole role;
  String text;

  Map<String, dynamic> toJson() => {
        'id': id,
        'role': role == ChatRole.user ? 'user' : 'assistant',
        'text': text,
      };

  static ChatMessage? fromJson(Map<String, dynamic> raw) {
    final role = raw['role'];
    final text = raw['text'];
    if (text is! String) return null;
    if (role != 'user' && role != 'assistant') return null;
    return ChatMessage(
      id: '${raw['id'] ?? newChatId()}',
      role: role == 'user' ? ChatRole.user : ChatRole.assistant,
      text: text,
    );
  }
}

String newChatId() =>
    'm${DateTime.now().microsecondsSinceEpoch.toRadixString(16)}';
