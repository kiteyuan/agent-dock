use std::fs;
use std::path::PathBuf;

use tauri::{LogicalPosition, LogicalSize, Manager, Position, Size, WebviewUrl, WebviewWindowBuilder};

fn device_auth_candidates() -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Ok(home) = std::env::var("AGENTDOCK_HOME") {
        let home = PathBuf::from(home);
        out.push(home.join("state").join("device-auth.json"));
        out.push(home.join("data").join("state").join("device-auth.json"));
    }
    out.push(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../data/state/device-auth.json"),
    );
    out
}

#[tauri::command]
fn local_device_token() -> Result<Option<String>, String> {
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

/// Resize while keeping the **bottom edge** fixed (grow/shrink upward).
#[tauri::command]
fn fit_pet_window(window: tauri::WebviewWindow, width: u32, height: u32) -> Result<(), String> {
    let w = f64::from(width.clamp(160, 640));
    let h = f64::from(height.clamp(180, 900));

    let scale = window.scale_factor().map_err(|e| e.to_string())?;
    let old_size = window.outer_size().map_err(|e| e.to_string())?.to_logical::<f64>(scale);
    let old_pos = window
        .outer_position()
        .map_err(|e| e.to_string())?
        .to_logical::<f64>(scale);

    let bottom = old_pos.y + old_size.height;
    let center_x = old_pos.x + old_size.width / 2.0;
    let mut new_x = center_x - w / 2.0;
    let mut new_y = bottom - h;

    if let Ok(Some(monitor)) = window.current_monitor() {
        let area = monitor.work_area();
        let pos = area.position.to_logical::<f64>(scale);
        let size = area.size.to_logical::<f64>(scale);
        let min_x = pos.x;
        let max_x = pos.x + size.width - w;
        let min_y = pos.y;
        let max_y = pos.y + size.height - h;
        new_x = new_x.clamp(min_x, max_x.max(min_x));
        new_y = new_y.clamp(min_y, max_y.max(min_y));
    }

    window
        .set_size(Size::Logical(LogicalSize {
            width: w,
            height: h,
        }))
        .map_err(|e| e.to_string())?;
    window
        .set_position(Position::Logical(LogicalPosition {
            x: new_x,
            y: new_y,
        }))
        .map_err(|e| e.to_string())?;
    Ok(())
}

fn place_bottom_right(window: &tauri::WebviewWindow) {
    let Ok(scale) = window.scale_factor() else {
        return;
    };
    let Ok(size) = window.outer_size() else {
        return;
    };
    let logical_size = size.to_logical::<f64>(scale);
    let margin = 16.0;
    let Ok(Some(monitor)) = window.current_monitor() else {
        return;
    };
    let area = monitor.work_area();
    let pos = area.position.to_logical::<f64>(scale);
    let area_size = area.size.to_logical::<f64>(scale);
    let x = pos.x + area_size.width - logical_size.width - margin;
    let y = pos.y + area_size.height - logical_size.height - margin;
    let _ = window.set_position(Position::Logical(LogicalPosition { x, y }));
}

fn admin_panel_url() -> String {
    std::env::var("AGENTDOCK_ADMIN_URL")
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "http://127.0.0.1:8766/admin/".to_string())
}

fn env_flag_true(name: &str) -> bool {
    matches!(
        std::env::var(name).ok().as_deref().map(str::trim),
        Some("1") | Some("true") | Some("TRUE") | Some("yes") | Some("YES")
    )
}

/// Open (or focus) the Runtime Admin console as a second app window.
#[tauri::command]
fn open_admin_panel(app: tauri::AppHandle) -> Result<(), String> {
    const LABEL: &str = "admin";
    if let Some(win) = app.get_webview_window(LABEL) {
        let _ = win.unminimize();
        let _ = win.show();
        let _ = win.set_focus();
        return Ok(());
    }
    let raw = admin_panel_url();
    let url = raw
        .parse::<url::Url>()
        .map_err(|e| format!("invalid admin URL {raw:?}: {e}"))?;
    WebviewWindowBuilder::new(&app, LABEL, WebviewUrl::External(url))
        .title("AgentDock 控制台")
        .inner_size(1120.0, 760.0)
        .min_inner_size(720.0, 480.0)
        .resizable(true)
        .decorations(true)
        .skip_taskbar(false)
        .center()
        .build()
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            local_device_token,
            fit_pet_window,
            open_admin_panel
        ])
        .setup(|app| {
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.set_skip_taskbar(true);
                place_bottom_right(&win);
            }
            if env_flag_true("AGENTDOCK_OPEN_ADMIN") {
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    // Admin HTTP is usually already up when start.* launches the pet.
                    std::thread::sleep(std::time::Duration::from_millis(800));
                    let _ = open_admin_panel(handle);
                });
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running AgentDock pet");
}
