//! Admin console: second window on loopback :8767 plus the allowlisted `admin_api` proxy.
//!
//! The console never talks HTTP to Runtime itself; every call goes through
//! [`admin_api`], which only forwards the `/api/v1/*` routes the UI needs.

use std::fs;
use std::time::Duration;

use serde::Serialize;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

use crate::{console_server, pet_window};

const ADMIN_API_ORIGIN: &str = "http://127.0.0.1:8766";
const ADMIN_LABEL: &str = "admin";

#[derive(Serialize)]
pub struct AdminApiResponse {
    status: u16,
    body: String,
}

fn seg_ok(s: &str) -> bool {
    !s.is_empty()
        && !s.contains("..")
        && s.chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
}

/// Narrow allowlist matching the desk-pet console UI.
fn admin_api_allowed(method: &str, path_with_query: &str) -> bool {
    if path_with_query.contains("://") || path_with_query.contains("..") {
        return false;
    }
    let path = path_with_query.split('?').next().unwrap_or(path_with_query);
    if !path.starts_with("/api/v1/") {
        return false;
    }
    let segs: Vec<&str> = path
        .trim_start_matches('/')
        .split('/')
        .filter(|s| !s.is_empty())
        .collect();
    match method {
        "GET" => match segs.as_slice() {
            ["api", "v1", "snapshot"]
            | ["api", "v1", "mcp"]
            | ["api", "v1", "notes", "graph"]
            | ["api", "v1", "notes", "doc"] => true,
            ["api", "v1", "jobs", id] => seg_ok(id),
            _ => false,
        },
        "POST" => match segs.as_slice() {
            ["api", "v1", "mcp"]
            | ["api", "v1", "llm", "shared"]
            | ["api", "v1", "pets", "import"] => true,
            ["api", "v1", "modules", kind, id, action] => {
                seg_ok(kind) && seg_ok(id) && seg_ok(action)
            }
            ["api", "v1", "agents", id, "settings"] => seg_ok(id),
            ["api", "v1", "defaults", kind] => seg_ok(kind),
            ["api", "v1", "licenses", module_id, license_id] => {
                seg_ok(module_id) && seg_ok(license_id)
            }
            ["api", "v1", "devices", id, "disconnect"] => seg_ok(id),
            _ => false,
        },
        _ => false,
    }
}

/// Proxy allowlisted Admin `/api/v1/*` through the host.
#[tauri::command]
pub async fn admin_api(
    method: String,
    path: String,
    body: Option<String>,
) -> Result<AdminApiResponse, String> {
    let path = path.trim();
    let method = method.trim().to_uppercase();
    if !admin_api_allowed(&method, path) {
        return Err(format!("admin_api denied: {method} {path}"));
    }
    let url = format!("{ADMIN_API_ORIGIN}{path}");
    let client = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(120))
        .build()
        .map_err(|e| e.to_string())?;
    let mut req = match method.as_str() {
        "GET" => client.get(&url),
        "POST" => client.post(&url),
        other => return Err(format!("unsupported method {other}")),
    };
    req = req.header("Content-Type", "application/json");
    if let (Some(b), "POST") = (body, method.as_str()) {
        req = req.body(b);
    }
    let response = req.send().await.map_err(|e| e.to_string())?;
    let status = response.status().as_u16();
    let body = response.text().await.map_err(|e| e.to_string())?;
    Ok(AdminApiResponse { status, body })
}

fn admin_window_position(app: &tauri::AppHandle) -> (f64, f64) {
    // Top-left of work area so the console does not cover the pet on open.
    app.get_webview_window(pet_window::MAIN_LABEL)
        .and_then(|main| {
            let monitor = main.current_monitor().ok().flatten()?;
            let scale = main.scale_factor().ok()?;
            let pos = monitor.work_area().position.to_logical::<f64>(scale);
            Some((pos.x + 24.0, pos.y + 24.0))
        })
        .unwrap_or((48.0, 48.0))
}

/// Open (or re-open) the Admin console as a second window.
///
/// Must be `async` on Windows: sync `WebviewWindowBuilder` deadlocks WebView2.
#[tauri::command]
pub async fn open_admin_panel(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window(ADMIN_LABEL) {
        let _ = win.close();
        std::thread::sleep(Duration::from_millis(200));
    }

    console_server::ensure_console_server()?;
    let parsed = console_server::console_index_url()
        .parse()
        .map_err(|e: url::ParseError| e.to_string())?;

    let (pos_x, pos_y) = admin_window_position(&app);
    let data_dir = app
        .path()
        .app_local_data_dir()
        .map_err(|e| e.to_string())?
        .join("admin-webview");
    let _ = fs::create_dir_all(&data_dir);

    WebviewWindowBuilder::new(&app, ADMIN_LABEL, WebviewUrl::External(parsed))
        .title("AgentDock 控制台")
        .inner_size(1120.0, 760.0)
        .min_inner_size(720.0, 480.0)
        .resizable(true)
        .decorations(true)
        .transparent(false)
        .always_on_top(false)
        .skip_taskbar(false)
        .data_directory(data_dir)
        .position(pos_x, pos_y)
        .on_navigation(|nav| {
            let host = nav.host_str().unwrap_or("");
            (host == "127.0.0.1" || host == "localhost")
                && nav.port_or_known_default() == Some(console_server::CONSOLE_PORT)
        })
        .build()
        .map_err(|e| e.to_string())?;
    pet_window::restore(&app);
    Ok(())
}

pub fn spawn_open_admin(app: tauri::AppHandle) {
    tauri::async_runtime::spawn(async move {
        if let Err(err) = open_admin_panel(app).await {
            eprintln!("[pet] open_admin_panel failed: {err}");
        }
    });
}

#[cfg(test)]
mod tests {
    use super::admin_api_allowed as ok;

    #[test]
    fn allows_console_routes() {
        assert!(ok("GET", "/api/v1/snapshot"));
        assert!(ok("GET", "/api/v1/notes/doc?path=a.md"));
        assert!(ok("GET", "/api/v1/jobs/abc-123"));
        assert!(ok("POST", "/api/v1/modules/tts/edge/install"));
        assert!(ok("POST", "/api/v1/devices/dev_1/disconnect"));
        assert!(ok("POST", "/api/v1/licenses/sovits/model.v2"));
    }

    #[test]
    fn rejects_everything_else() {
        assert!(!ok("DELETE", "/api/v1/snapshot"));
        assert!(!ok("POST", "/api/v1/snapshot"));
        assert!(!ok("GET", "/api/snapshot"));
        assert!(!ok("GET", "/mcp"));
        assert!(!ok("GET", "/api/v1/jobs/a/b"));
        assert!(!ok("GET", "/api/v1/../admin"));
        assert!(!ok("GET", "http://evil/api/v1/snapshot"));
        assert!(!ok("POST", "/api/v1/modules/tts/ed%2F/install/x"));
        assert!(!ok("POST", "/api/v1/agents/a b/settings"));
    }
}
