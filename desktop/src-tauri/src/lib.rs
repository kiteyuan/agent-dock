mod admin;
mod auth;
mod console_server;
mod pet_window;
mod runtime_child;
mod tray;

use std::time::Duration;

use tauri::{Manager, RunEvent};

pub(crate) fn env_flag_true(name: &str) -> bool {
    matches!(
        std::env::var(name).ok().as_deref().map(str::trim),
        Some("1") | Some("true") | Some("TRUE") | Some("yes") | Some("YES")
    )
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

fn wait_for_admin_http() {
    for _ in 0..40 {
        if std::net::TcpStream::connect_timeout(
            &([127, 0, 0, 1], 8766).into(),
            Duration::from_millis(200),
        )
        .is_ok()
        {
            return;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(pet_window::PetHitState::default())
        .invoke_handler(tauri::generate_handler![
            auth::local_device_token,
            auth::secure_device_token_get,
            auth::secure_device_token_set,
            auth::secure_device_token_clear,
            pet_window::fit_pet_window,
            pet_window::start_pet_drag,
            pet_window::pet_window_pos,
            pet_window::set_pet_window_pos,
            pet_window::set_pet_hit_rects,
            admin::open_admin_panel,
            admin::admin_api,
            shutdown_host
        ])
        .setup(|app| {
            match runtime_child::ensure_runtime() {
                // Wait briefly for Admin HTTP before opening console / UI calls.
                Ok(true) => wait_for_admin_http(),
                Ok(false) => {}
                Err(err) => eprintln!("[pet] Runtime spawn: {err}"),
            }
            if let Err(err) = console_server::ensure_console_server() {
                eprintln!("[pet] console static server: {err}");
            }
            if let Some(win) = app.get_webview_window(pet_window::MAIN_LABEL) {
                let _ = win.set_skip_taskbar(true);
                pet_window::place_bottom_right(&win);
            }
            pet_window::spawn_hit_test(app.handle().clone());
            tray::build(app)?;

            if env_flag_true("AGENTDOCK_OPEN_ADMIN") {
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_millis(1200));
                    admin::spawn_open_admin(handle);
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
