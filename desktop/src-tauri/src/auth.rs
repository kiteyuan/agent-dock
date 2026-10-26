//! Device token for the Runtime WebSocket: OS keyring first, local Runtime file as bootstrap.

use std::fs;
use std::path::PathBuf;

const KEYRING_SERVICE: &str = "com.agentdock.pet";
const KEYRING_ACCOUNT: &str = "device_token";

fn device_auth_candidates() -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Ok(home) = std::env::var("AGENTDOCK_HOME") {
        let home = PathBuf::from(home);
        out.push(home.join("state").join("device-auth.json"));
        out.push(home.join("data").join("state").join("device-auth.json"));
    }
    out.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../data/state/device-auth.json"));
    out
}

#[tauri::command]
pub fn local_device_token() -> Result<Option<String>, String> {
    for path in device_auth_candidates() {
        let Ok(path) = path.canonicalize() else {
            continue;
        };
        let Ok(raw) = fs::read_to_string(&path) else {
            continue;
        };
        let Ok(val) = serde_json::from_str::<serde_json::Value>(&raw) else {
            continue;
        };
        let token = val
            .get("token")
            .and_then(|v| v.as_str())
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string);
        if token.is_some() {
            return Ok(token);
        }
    }
    Ok(None)
}

fn token_entry() -> Result<keyring::Entry, String> {
    keyring::Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn secure_device_token_get() -> Result<Option<String>, String> {
    match token_entry()?.get_password() {
        Ok(p) => {
            let t = p.trim();
            Ok((!t.is_empty()).then(|| t.to_string()))
        }
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
pub fn secure_device_token_set(token: String) -> Result<(), String> {
    let t = token.trim();
    if t.is_empty() {
        return secure_device_token_clear();
    }
    token_entry()?.set_password(t).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn secure_device_token_clear() -> Result<(), String> {
    match token_entry()?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}
