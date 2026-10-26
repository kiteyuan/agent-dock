//! Main pet window: bottom-pinned sizing, manual drag, and click-through of transparent areas.

use std::sync::Mutex;
use std::time::Duration;

use tauri::{LogicalPosition, Manager, Position};
#[cfg(not(windows))]
use tauri::{LogicalSize, Size};

pub const MAIN_LABEL: &str = "main";

fn main_window(app: &tauri::AppHandle) -> Result<tauri::WebviewWindow, String> {
    app.get_webview_window(MAIN_LABEL)
        .ok_or_else(|| "main pet window missing".to_string())
}

/// Resize while keeping the **bottom edge** fixed (grow/shrink upward).
///
/// When the requested width matches the current width (normal confirm / reply
/// height tweaks), **keep X unchanged**. Re-deriving X from `right - w` every
/// time used to walk the window sideways on DPI round-trip even when width
/// was intentionally stable.
#[tauri::command]
pub fn fit_pet_window(window: tauri::WebviewWindow, width: u32, height: u32) -> Result<(), String> {
    let scale = window.scale_factor().map_err(|e| e.to_string())?;
    let old_size = window
        .outer_size()
        .map_err(|e| e.to_string())?
        .to_logical::<f64>(scale);
    let old_pos = window
        .outer_position()
        .map_err(|e| e.to_string())?
        .to_logical::<f64>(scale);

    // Cap to the monitor work area — a hard 900px ceiling was clipping long replies.
    let (max_w, max_h) = if let Ok(Some(monitor)) = window.current_monitor() {
        let area = monitor.work_area();
        let size = area.size.to_logical::<f64>(scale);
        (
            (size.width - 16.0).max(160.0),
            (size.height - 16.0).max(180.0),
        )
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
        let max_x = pos.x + size.width - w;
        let max_y = pos.y + size.height - h;
        new_x = new_x.clamp(pos.x, max_x.max(pos.x));
        new_y = new_y.clamp(pos.y, max_y.max(pos.y));
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
        set_bounds_atomic(&window, scale, width_same, y_clamped, new_x, new_y, w, h)?;
    }
    #[cfg(not(windows))]
    {
        let _ = y_clamped;
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
                .set_position(Position::Logical(LogicalPosition { x: new_x, y: new_y }))
                .map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

/// Position + size in one `SetWindowPos`, bottom edge pinned in physical pixels.
#[cfg(windows)]
#[allow(clippy::too_many_arguments)]
fn set_bounds_atomic(
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
    // SAFETY: `hwnd` is the live top-level window owned by this process.
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

pub fn place_bottom_right(window: &tauri::WebviewWindow) {
    let Ok(scale) = window.scale_factor() else {
        return;
    };
    let Ok(size) = window.outer_size() else {
        return;
    };
    let Ok(Some(monitor)) = window.current_monitor() else {
        return;
    };
    let logical_size = size.to_logical::<f64>(scale);
    let margin = 16.0;
    let area = monitor.work_area();
    let pos = area.position.to_logical::<f64>(scale);
    let area_size = area.size.to_logical::<f64>(scale);
    let x = pos.x + area_size.width - logical_size.width - margin;
    let y = pos.y + area_size.height - logical_size.height - margin;
    let _ = window.set_position(Position::Logical(LogicalPosition { x, y }));
}

/// OS drag of the main pet window (do not rely on getCurrentWindow after multi-window).
#[tauri::command]
pub fn start_pet_drag(app: tauri::AppHandle) -> Result<(), String> {
    main_window(&app)?
        .start_dragging()
        .map_err(|e| e.to_string())
}

/// Current main-window outer position in logical pixels.
#[tauri::command]
pub fn pet_window_pos(app: tauri::AppHandle) -> Result<(f64, f64), String> {
    let win = main_window(&app)?;
    let scale = win.scale_factor().map_err(|e| e.to_string())?;
    let pos = win
        .outer_position()
        .map_err(|e| e.to_string())?
        .to_logical::<f64>(scale);
    Ok((pos.x, pos.y))
}

/// Set main-window outer position (logical px). Used for smooth manual drag.
#[tauri::command]
pub fn set_pet_window_pos(app: tauri::AppHandle, x: f64, y: f64) -> Result<(), String> {
    if !x.is_finite() || !y.is_finite() {
        return Ok(());
    }
    main_window(&app)?
        .set_position(Position::Logical(LogicalPosition { x, y }))
        .map_err(|e| e.to_string())
}

/// Interactive regions of the pet window (client-area CSS px: x, y, w, h).
/// `None` = whole window is interactive (boot, drag, settings dialog).
#[derive(Default)]
pub struct PetHitState {
    rects: Mutex<Option<Vec<[f64; 4]>>>,
}

#[tauri::command]
pub fn set_pet_hit_rects(state: tauri::State<'_, PetHitState>, rects: Option<Vec<[f64; 4]>>) {
    if let Ok(mut guard) = state.rects.lock() {
        *guard = rects;
    }
}

fn point_in_rects(rects: &[[f64; 4]], x: f64, y: f64) -> bool {
    rects
        .iter()
        .any(|r| x >= r[0] && y >= r[1] && x <= r[0] + r[2] && y <= r[1] + r[3])
}

/// Click-through for the transparent part of the fixed-size pet window: poll the
/// cursor and toggle ignore-cursor-events when it leaves/enters a hit rect.
/// Polling (not hooks) because a click-through window receives no mouse events.
pub fn spawn_hit_test(app: tauri::AppHandle) {
    std::thread::Builder::new()
        .name("pet-hit-test".into())
        .spawn(move || {
            let mut ignoring = false;
            loop {
                std::thread::sleep(Duration::from_millis(33));
                let Some(win) = app.get_webview_window(MAIN_LABEL) else {
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
                    Some(!point_in_rects(&rects, x, y))
                })()
                .unwrap_or(false);
                if want_ignore != ignoring && win.set_ignore_cursor_events(want_ignore).is_ok() {
                    ignoring = want_ignore;
                }
            }
        })
        .expect("spawn pet hit-test thread");
}

pub fn restore(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window(MAIN_LABEL) {
        let _ = win.set_ignore_cursor_events(false);
        let _ = win.set_always_on_top(true);
        let _ = win.set_skip_taskbar(true);
        let _ = win.show();
    }
}

#[cfg(test)]
mod tests {
    use super::point_in_rects;

    #[test]
    fn hit_rects_are_inclusive_and_any_match_wins() {
        let rects = [[10.0, 10.0, 20.0, 20.0], [100.0, 0.0, 5.0, 5.0]];
        assert!(point_in_rects(&rects, 10.0, 10.0));
        assert!(point_in_rects(&rects, 30.0, 30.0));
        assert!(point_in_rects(&rects, 102.0, 3.0));
        assert!(!point_in_rects(&rects, 31.0, 15.0));
        assert!(!point_in_rects(&[], 0.0, 0.0));
    }
}
