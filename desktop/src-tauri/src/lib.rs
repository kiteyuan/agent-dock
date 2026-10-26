mod console_server;
mod runtime_child;

use std::fs;
use std::path::PathBuf;
use std::time::Duration;

use serde::Serialize;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{LogicalPosition, Manager, Position, RunEvent, WebviewUrl, WebviewWindowBuilder};
#[cfg(not(windows))]
use tauri::{LogicalSize, Size};

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

const KEYRING_SERVICE: &str = "com.agentdock.pet";
const KEYRING_ACCOUNT: &str = "device_token";

fn token_entry() -> Result<keyring::Entry, String> {
    keyring::Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT).map_err(|e| e.to_string())
}

#[tauri::command]
fn secure_device_token_get() -> Result<Option<String>, String> {
    match token_entry()?.get_password() {
        Ok(p) => {
            let t = p.trim();
            if t.is_empty() {
                Ok(None)
            } else {
                Ok(Some(t.to_string()))
            }
        }
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
fn secure_device_token_set(token: String) -> Result<(), String> {
    let t = token.trim();
    if t.is_empty() {
        return secure_device_token_clear();
    }
    token_entry()?
        .set_password(t)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn secure_device_token_clear() -> Result<(), String> {
    match token_entry()?.delete_credential() {
        Ok(()) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

/// Resize while keeping the **bottom edge** fixed (grow/shrink upward).
///
/// When the requested width matches the current width (normal confirm / reply
/// height tweaks), **keep X unchanged**. Re-deriving X from `right - w` every
/// time used to walk the window sideways on DPI round-trip even when width
/// was intentionally stable.
#[tauri::command]
fn fit_pet_window(window: tauri::WebviewWindow, width: u32, height: u32) -> Result<(), String> {
    let scale = window.scale_factor().map_err(|e| e.to_string())?;
    let old_size = window.outer_size().map_err(|e| e.to_string())?.to_logical::<f64>(scale);
    let old_pos = window
        .outer_position()
        .map_err(|e| e.to_string())?
        .to_logical::<f64>(scale);

    // Cap to the monitor work area — a hard 900px ceiling was clipping long replies.
    let (max_w, max_h) = if let Ok(Some(monitor)) = window.current_monitor() {
        let area = monitor.work_area();
        let size = area.size.to_logical::<f64>(scale);
        ((size.width - 16.0).max(160.0), (size.height - 16.0).max(180.0))
    } else {
        (640.0, 2400.0)
    };
    let w = f64::from(width).clamp(160.0, max_w);
    let h = f64::from(height).clamp(180.0, max_h);

    let width_same = (old_size.width - w).abs() < 2.0;
    let bottom = old_pos.y + old_size.height;
    let mut new_x = if width_same {
        old_pos.x
    } else {
        // Real width change (e.g. compact toggle): pin the right edge.
        old_pos.x + old_size.width - w
    };
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

    let pinned_y = bottom - h;
    let height_same = (old_size.height - h).abs() < 2.0;
    let pos_same = (old_pos.x - new_x).abs() < 1.0 && (old_pos.y - new_y).abs() < 1.0;
    if width_same && height_same && pos_same {
        return Ok(());
    }

    // One OS call. set_size then set_position lets Windows keep the top-left for a
    // frame, so the bottom (and the pet) drops and snaps back.
    let y_clamped = (new_y - pinned_y).abs() > 0.5;
    #[cfg(windows)]
    {
        set_pet_bounds_atomic(&window, scale, width_same, y_clamped, new_x, new_y, w, h)?;
    }
    #[cfg(not(windows))]
    {
        if !width_same || !height_same {
            window
                .set_size(Size::Logical(LogicalSize {
                    width: if width_same { old_size.width } else { w },
                    height: h,
                }))
                .map_err(|e| e.to_string())?;
        }
        if !pos_same {
            window
                .set_position(Position::Logical(LogicalPosition {
                    x: new_x,
                    y: new_y,
                }))
                .map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

/// Position + size in one `SetWindowPos`, bottom edge pinned in physical pixels.
#[cfg(windows)]
fn set_pet_bounds_atomic(
    window: &tauri::WebviewWindow,
    scale: f64,
    width_same: bool,
    y_clamped: bool,
    x: f64,
    y: f64,
    w: f64,
    h: f64,
) -> Result<(), String> {
    use windows::Win32::UI::WindowsAndMessaging::{
        SetWindowPos, SWP_NOACTIVATE, SWP_NOCOPYBITS, SWP_NOZORDER,
    };

    let old_pos = window.outer_position().map_err(|e| e.to_string())?;
    let old_size = window.outer_size().map_err(|e| e.to_string())?;
    let ph = (h * scale).round() as i32;
    let pw = if width_same {
        old_size.width as i32
    } else {
        (w * scale).round() as i32
    };
    let px = if width_same {
        old_pos.x
    } else {
        (x * scale).round() as i32
    };
    let py = if y_clamped {
        (y * scale).round() as i32
    } else {
        old_pos.y + old_size.height as i32 - ph
    };

    let hwnd = window.hwnd().map_err(|e| e.to_string())?;
    unsafe {
        SetWindowPos(
            hwnd,
            None,
            px,
            py,
            pw,
            ph,
            SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOCOPYBITS,
        )
        .map_err(|e| e.to_string())?;
    }
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

fn env_flag_true(name: &str) -> bool {
    matches!(
        std::env::var(name).ok().as_deref().map(str::trim),
        Some("1") | Some("true") | Some("TRUE") | Some("yes") | Some("YES")
    )
}

/// Drag the main pet window (do not rely on getCurrentWindow after multi-window).
/// Prefer [`nudge_pet_window`] on Windows — OS `start_dragging` draws a full HWND outline box.
#[tauri::command]
fn start_pet_drag(app: tauri::AppHandle) -> Result<(), String> {
    let win = app
        .get_webview_window("main")
        .ok_or_else(|| "main pet window missing".to_string())?;
    win.start_dragging().map_err(|e| e.to_string())
}

/// Current main-window outer position in logical pixels.
#[tauri::command]
fn pet_window_pos(app: tauri::AppHandle) -> Result<(f64, f64), String> {
    let win = app
        .get_webview_window("main")
        .ok_or_else(|| "main pet window missing".to_string())?;
    let scale = win.scale_factor().map_err(|e| e.to_string())?;
    let pos = win
        .outer_position()
        .map_err(|e| e.to_string())?
        .to_logical::<f64>(scale);
    Ok((pos.x, pos.y))
}

/// Set main-window outer position (logical px). Used for smooth manual drag.
#[tauri::command]
fn set_pet_window_pos(app: tauri::AppHandle, x: f64, y: f64) -> Result<(), String> {
    let win = app
        .get_webview_window("main")
        .ok_or_else(|| "main pet window missing".to_string())?;
    if !x.is_finite() || !y.is_finite() {
        return Ok(());
    }
    win.set_position(Position::Logical(LogicalPosition { x, y }))
        .map_err(|e| e.to_string())
}

/// Interactive regions of the pet window (client-area CSS px: x, y, w, h).
/// `None` = whole window is interactive (boot, drag, settings dialog).
#[derive(Default)]
struct PetHitState {
    rects: std::sync::Mutex<Option<Vec<[f64; 4]>>>,
}

#[tauri::command]
fn set_pet_hit_rects(state: tauri::State<'_, PetHitState>, rects: Option<Vec<[f64; 4]>>) {
    if let Ok(mut guard) = state.rects.lock() {
        *guard = rects;
    }
}

/// Click-through for the transparent part of the fixed-size pet window: poll the
/// cursor and toggle ignore-cursor-events when it leaves/enters a hit rect.
fn spawn_pet_hit_test(app: tauri::AppHandle) {
    std::thread::spawn(move || {
        let mut ignoring = false;
        loop {
            std::thread::sleep(Duration::from_millis(33));
            let Some(win) = app.get_webview_window("main") else {
                continue;
            };
            let want_ignore = (|| -> Option<bool> {
                let rects = app.state::<PetHitState>().rects.lock().ok()?.clone()?;
                if !win.is_visible().ok()? {
                    return None;
                }
                let cursor = app.cursor_position().ok()?;
                let origin = win.inner_position().ok()?;
                let scale = win.scale_factor().ok()?;
                let x = (cursor.x - f64::from(origin.x)) / scale;
                let y = (cursor.y - f64::from(origin.y)) / scale;
                let inside = rects
                    .iter()
                    .any(|r| x >= r[0] && y >= r[1] && x <= r[0] + r[2] && y <= r[1] + r[3]);
                Some(!inside)
            })()
            .unwrap_or(false);
            if want_ignore != ignoring && win.set_ignore_cursor_events(want_ignore).is_ok() {
                ignoring = want_ignore;
            }
        }
    });
}

fn restore_pet_window(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.set_ignore_cursor_events(false);
        let _ = win.set_always_on_top(true);
        let _ = win.set_skip_taskbar(true);
        let _ = win.show();
    }
}

const ADMIN_API_ORIGIN: &str = "http://127.0.0.1:8766";

#[derive(Serialize)]
struct AdminApiResponse {
    status: u16,
    body: String,
}

fn path_segments(path: &str) -> Vec<&str> {
    path.trim_start_matches('/')
        .split('/')
        .filter(|s| !s.is_empty())
        .collect()
}

fn seg_ok(s: &str) -> bool {
    !s.is_empty()
        && !s.contains("..")
        && s.chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
}

/// Narrow allowlist matching the desk-pet console UI (Chromium-style capability surface).
fn admin_api_allowed(method: &str, path_with_query: &str) -> bool {
    if path_with_query.contains("://") || path_with_query.contains("..") {
        return false;
    }
    let path = path_with_query.split('?').next().unwrap_or(path_with_query);
    if !path.starts_with("/api/v1/") {
        return false;
    }
    let segs = path_segments(path);
    // ["api", "v1", ...]
    if segs.len() < 3 || segs[0] != "api" || segs[1] != "v1" {
        return false;
    }
    match method {
        "GET" => match segs.as_slice() {
            ["api", "v1", "snapshot"] => true,
            ["api", "v1", "mcp"] => true,
            ["api", "v1", "notes", "graph"] => true,
            ["api", "v1", "notes", "doc"] => true,
            ["api", "v1", "jobs", id] if seg_ok(id) => true,
            _ => false,
        },
        "POST" => match segs.as_slice() {
            ["api", "v1", "mcp"] => true,
            ["api", "v1", "llm", "shared"] => true,
            ["api", "v1", "pets", "import"] => true,
            ["api", "v1", "modules", kind, id, action]
                if seg_ok(kind) && seg_ok(id) && seg_ok(action) =>
            {
                true
            }
            ["api", "v1", "agents", id, "settings"] if seg_ok(id) => true,
            ["api", "v1", "defaults", kind] if seg_ok(kind) => true,
            ["api", "v1", "licenses", module_id, license_id]
                if seg_ok(module_id) && seg_ok(license_id) =>
            {
                true
            }
            ["api", "v1", "devices", id, "disconnect"] if seg_ok(id) => true,
            _ => false,
        },
        _ => false,
    }
}

/// Proxy allowlisted Admin `/api/v1/*` through the host. Console never talks HTTP itself.
#[tauri::command]
async fn admin_api(
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
    if let Some(b) = body {
        if method == "POST" {
            req = req.body(b);
        }
    }
    let response = req.send().await.map_err(|e| e.to_string())?;
    let status = response.status().as_u16();
    let body = response.text().await.map_err(|e| e.to_string())?;
    Ok(AdminApiResponse { status, body })
}

fn admin_window_position(app: &tauri::AppHandle) -> (f64, f64) {
    // Top-left of work area so the console does not cover the pet on open.
    if let Some(main) = app.get_webview_window("main") {
        if let Some((x, y)) = main
            .current_monitor()
            .ok()
            .flatten()
            .and_then(|m| {
                let scale = main.scale_factor().ok()?;
                let area = m.work_area();
                let pos = area.position.to_logical::<f64>(scale);
                Some((pos.x + 24.0, pos.y + 24.0))
            })
        {
            return (x, y);
        }
    }
    (48.0, 48.0)
}

/// Open (or focus) the Admin console as a second window.
///
/// Must be `async` on Windows: sync `WebviewWindowBuilder` deadlocks WebView2.
/// UI is served from loopback **:8767** (`desktop/web/console`). API goes through
/// allowlisted `admin_api` — Runtime does **not** host Admin HTML.
#[tauri::command]
async fn open_admin_panel(app: tauri::AppHandle) -> Result<(), String> {
    const LABEL: &str = "admin";
    if let Some(win) = app.get_webview_window(LABEL) {
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

    WebviewWindowBuilder::new(&app, LABEL, WebviewUrl::External(parsed))
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
            let port = nav.port_or_known_default();
            (host == "127.0.0.1" || host == "localhost")
                && port == Some(console_server::CONSOLE_PORT)
        })
        .build()
        .map_err(|e| e.to_string())?;
    restore_pet_window(&app);
    Ok(())
}

fn spawn_open_admin(app: tauri::AppHandle) {
    tauri::async_runtime::spawn(async move {
        if let Err(err) = open_admin_panel(app.clone()).await {
            eprintln!("[pet] open_admin_panel failed: {err}");
        }
    });
}

/// Full host stop — sidecars + Runtime ports + exit pet (scripts/stop.* equivalent).
#[tauri::command]
fn shutdown_host(app: tauri::AppHandle) -> Result<(), String> {
    eprintln!("[pet] shutdown_host requested");
    // Run blocking stop off the main thread so WebView can paint "closing…".
    std::thread::spawn(move || {
        runtime_child::shutdown_runtime_stack();
        app.exit(0);
    });
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(PetHitState::default())
        .invoke_handler(tauri::generate_handler![
            local_device_token,
            secure_device_token_get,
            secure_device_token_set,
            secure_device_token_clear,
            fit_pet_window,
            start_pet_drag,
            pet_window_pos,
            set_pet_window_pos,
            set_pet_hit_rects,
            open_admin_panel,
            admin_api,
            shutdown_host
        ])
        .setup(|app| {
            match runtime_child::ensure_runtime() {
                Ok(owned) => {
                    if owned {
                        // Wait briefly for Admin HTTP before opening console / UI calls.
                        for _ in 0..40 {
                            if std::net::TcpStream::connect_timeout(
                                &([127, 0, 0, 1], 8766).into(),
                                Duration::from_millis(200),
                            )
                            .is_ok()
                            {
                                break;
                            }
                            std::thread::sleep(Duration::from_millis(250));
                        }
                    }
                }
                Err(err) => eprintln!("[pet] Runtime spawn: {err}"),
            }

            if let Err(err) = console_server::ensure_console_server() {
                eprintln!("[pet] console static server: {err}");
            }
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.set_skip_taskbar(true);
                place_bottom_right(&win);
            }
            spawn_pet_hit_test(app.handle().clone());

            let admin_item = MenuItem::with_id(app, "tray-admin", "打开控制台", true, None::<&str>)?;
            let restart_rt = MenuItem::with_id(
                app,
                "tray-restart-runtime",
                "重启 Runtime",
                true,
                None::<&str>,
            )?;
            let sep = PredefinedMenuItem::separator(app)?;
            let quit_item = MenuItem::with_id(app, "tray-quit", "退出桌宠", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&admin_item, &restart_rt, &sep, &quit_item])?;
            let mut tray = TrayIconBuilder::with_id("pet-tray")
                .menu(&menu)
                .tooltip("AgentDock Pet")
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "tray-admin" => spawn_open_admin(app.clone()),
                    "tray-restart-runtime" => {
                        if !runtime_child::we_own_runtime() {
                            eprintln!("[pet] restart skipped — Runtime not pet-owned (external)");
                            return;
                        }
                        if let Err(err) = runtime_child::restart_owned() {
                            eprintln!("[pet] restart Runtime failed: {err}");
                        }
                    }
                    "tray-quit" => {
                        runtime_child::stop_owned();
                        app.exit(0);
                    }
                    _ => {}
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.build(app)?;

            if env_flag_true("AGENTDOCK_OPEN_ADMIN") {
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(std::time::Duration::from_millis(1200));
                    spawn_open_admin(handle);
                });
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building AgentDock pet")
        .run(|_app, event| {
            if let RunEvent::Exit = event {
                runtime_child::stop_owned();
            }
        });
}
