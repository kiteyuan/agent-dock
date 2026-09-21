enum ClientState {
  offline,
  connecting,
  idle,
  listening,
  busy,
  speaking,
  error,
}

extension ClientStateLabel on ClientState {
  String get label => switch (this) {
        ClientState.offline => '未连接',
        ClientState.connecting => '连接中',
        ClientState.idle => '在线',
        ClientState.listening => '听着',
        ClientState.busy => '…',
        ClientState.speaking => '播放中',
        ClientState.error => '错误',
      };

  bool get canToggleTalk =>
      this == ClientState.idle ||
      this == ClientState.listening ||
      this == ClientState.busy ||
      this == ClientState.speaking;
}
