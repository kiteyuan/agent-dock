//! System tray: open console, restart pet-owned Runtime, quit.

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;

use crate::{admin, runtime_child};

pub fn build(app: &tauri::App) -> tauri::Result<()> {
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
            "tray-admin" => admin::spawn_open_admin(app.clone()),
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
    Ok(())
}
