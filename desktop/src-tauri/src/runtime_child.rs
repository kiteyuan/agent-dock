//! Desk-pet owns the Runtime process when it starts it.
//!
//! If `:8765` is already listening (or `AGENTDOCK_EXTERNAL_RUNTIME=1`), we do
//! not spawn and will not kill on exit.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

static OWNED: Mutex<Option<Child>> = Mutex::new(None);

fn env_flag_true(name: &str) -> bool {
    matches!(
        std::env::var(name).ok().as_deref().map(str::trim),
        Some("1") | Some("true") | Some("TRUE") | Some("yes") | Some("YES")
    )
}

fn port_open(port: u16) -> bool {
    TcpStream::connect_timeout(
        &([127, 0, 0, 1], port).into(),
        Duration::from_millis(200),
    )
    .is_ok()
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.."))
}

fn python_cmd() -> String {
    std::env::var("AGENTDOCK_PYTHON").unwrap_or_else(|_| "python".into())
}

fn append_log_header(log_path: &PathBuf, title: &str) {
    if let Some(parent) = log_path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(log_path) {
        let _ = writeln!(f, "\n==== {} {title} ====", chrono_like_stamp());
    }
}

fn chrono_like_stamp() -> String {
    // Avoid extra chrono dep — local time via system.
    format!("{:?}", std::time::SystemTime::now())
}

/// Spawn Runtime if needed. Returns whether this process owns the child.
pub fn ensure_runtime() -> Result<bool, String> {
    if env_flag_true("AGENTDOCK_EXTERNAL_RUNTIME") {
        eprintln!("[pet] AGENTDOCK_EXTERNAL_RUNTIME=1 — not spawning Runtime");
        return Ok(false);
    }
    if port_open(8765) {
        eprintln!("[pet] Runtime already on :8765 — external, will not kill on exit");
        return Ok(false);
    }

    let root = repo_root();
    let log_path = root.join("data/logs/runtime.log");
    append_log_header(&log_path, "Runtime (pet-owned)");

    let log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|e| format!("runtime.log: {e}"))?;
    let log_err = log_file
        .try_clone()
        .map_err(|e| format!("runtime.log clone: {e}"))?;

    let mut cmd = Command::new(python_cmd());
    cmd.args(["-m", "runtime"])
        .current_dir(&root)
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::from(log_file))
        .stderr(Stdio::from(log_err));

    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);

    let child = cmd
        .spawn()
        .map_err(|e| format!("spawn python -m runtime failed: {e}"))?;

    eprintln!(
        "[pet] spawned Runtime pid={} cwd={}",
        child.id(),
        root.display()
    );

    let mut guard = OWNED.lock().map_err(|e| e.to_string())?;
    *guard = Some(child);
    Ok(true)
}

pub fn we_own_runtime() -> bool {
    OWNED
        .lock()
        .map(|g| g.is_some())
        .unwrap_or(false)
}

/// Kill Runtime only if we spawned it.
pub fn stop_owned() {
    let mut guard = match OWNED.lock() {
        Ok(g) => g,
        Err(_) => return,
    };
    if let Some(mut child) = guard.take() {
        let pid = child.id();
        eprintln!("[pet] stopping owned Runtime pid={pid}");
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// Best-effort stop of managed sidecars via Admin HTTP, then kill owned Runtime.
/// Optionally frees :8765/:8766 listeners (stop.ps1-like) when still held.
pub fn shutdown_runtime_stack() {
    // Sync HTTP — fine for quit path.
    let client = match reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(6))
        .redirect(reqwest::redirect::Policy::none())
        .build()
    {
        Ok(c) => c,
        Err(_) => {
            stop_owned();
            return;
        }
    };
    if let Ok(resp) = client
        .get("http://127.0.0.1:8766/api/v1/snapshot")
        .send()
    {
        if let Ok(snap) = resp.json::<serde_json::Value>() {
            if let Some(services) = snap.get("services").and_then(|v| v.as_array()) {
                for s in services {
                    let can = s
                        .get("can_stop")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false)
                        || s.get("owned").and_then(|v| v.as_bool()).unwrap_or(false);
                    let Some(id) = s.get("id").and_then(|v| v.as_str()) else {
                        continue;
                    };
                    if !can || id.is_empty() {
                        continue;
                    }
                    let url = format!("http://127.0.0.1:8766/api/v1/modules/service/{id}/stop");
                    let _ = client
                        .post(&url)
                        .header("Content-Type", "application/json")
                        .body("{}")
                        .send();
                }
            }
        }
    }

    stop_owned();
    std::thread::sleep(Duration::from_millis(300));

    // Like stop.ps1: free Runtime ports if something is still listening.
    #[cfg(windows)]
    {
        let _ = Command::new("powershell.exe")
            .args([
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "foreach ($port in 8765,8766) { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }",
            ])
            .creation_flags(CREATE_NO_WINDOW)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    #[cfg(not(windows))]
    {
        for port in [8765u16, 8766] {
            let _ = Command::new("sh")
                .args([
                    "-c",
                    &format!(
                        "pids=$(lsof -tiTCP:{port} -sTCP:LISTEN 2>/dev/null); [ -n \"$pids\" ] && kill -TERM $pids 2>/dev/null; sleep 0.2; [ -n \"$pids\" ] && kill -KILL $pids 2>/dev/null; true"
                    ),
                ])
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }
    }
}

/// Restart only when we own the child (or adopt by spawning fresh if port free).
pub fn restart_owned() -> Result<(), String> {
    stop_owned();
    // Brief wait so :8765 releases.
    std::thread::sleep(Duration::from_millis(400));
    if port_open(8765) {
        return Err("Runtime port :8765 still held by another process".into());
    }
    let _ = ensure_runtime()?;
    // Wait until Admin HTTP is up (best-effort).
    for _ in 0..60 {
        if port_open(8766) {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    Err("Runtime started but :8766 not ready".into())
}
