//! Loopback-only static file server for the Admin console Dist on **:8767**.
//!
//! WebView2 loads Vite ESM unreliably over Tauri's App custom protocol.
//! Fixed port lets capabilities pin `remote.urls` (no wildcard ports).

use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Component, Path, PathBuf};
use std::sync::OnceLock;
use std::thread;

pub const CONSOLE_PORT: u16 = 8767;

static STARTED: OnceLock<()> = OnceLock::new();

fn console_root() -> Result<PathBuf, String> {
    let candidates = [
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../web/console"),
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../desktop/web/console"),
    ];
    for c in candidates {
        if let Ok(p) = c.canonicalize() {
            if p.join("index.html").is_file() {
                return Ok(p);
            }
        }
    }
    Err("desktop/web/console/index.html missing — run: cd runtime/admin/ui && npm run build".into())
}

fn mime_for(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase()
        .as_str()
    {
        "html" => "text/html; charset=utf-8",
        "js" | "mjs" => "text/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" => "application/json; charset=utf-8",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "ico" => "image/x-icon",
        "webp" => "image/webp",
        "woff2" => "font/woff2",
        "map" => "application/json",
        _ => "application/octet-stream",
    }
}

fn safe_join(root: &Path, url_path: &str) -> Option<PathBuf> {
    let decoded = url_path.split('?').next().unwrap_or(url_path);
    let decoded = percent_decode(decoded);
    let rel = decoded.trim_start_matches('/');
    let rel = if rel.is_empty() { "index.html" } else { rel };
    let mut out = root.to_path_buf();
    for part in Path::new(rel).components() {
        match part {
            Component::Normal(p) => out.push(p),
            Component::CurDir => {}
            _ => return None,
        }
    }
    let canon = out.canonicalize().ok()?;
    if !canon.starts_with(root) {
        return None;
    }
    if canon.is_dir() {
        let index = canon.join("index.html");
        if index.is_file() {
            return Some(index);
        }
        return None;
    }
    if canon.is_file() {
        Some(canon)
    } else {
        None
    }
}

fn percent_decode(input: &str) -> String {
    let bytes = input.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let Ok(v) = u8::from_str_radix(
                std::str::from_utf8(&bytes[i + 1..i + 3]).unwrap_or(""),
                16,
            ) {
                out.push(v);
                i += 3;
                continue;
            }
        }
        out.push(if bytes[i] == b'+' { b' ' } else { bytes[i] });
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn handle_client(mut stream: TcpStream, root: &Path) {
    let mut buf = [0u8; 4096];
    let n = match stream.read(&mut buf) {
        Ok(0) | Err(_) => return,
        Ok(n) => n,
    };
    let req = String::from_utf8_lossy(&buf[..n]);
    let mut lines = req.lines();
    let Some(first) = lines.next() else {
        return;
    };
    let mut parts = first.split_whitespace();
    let method = parts.next().unwrap_or("");
    let path = parts.next().unwrap_or("/");
    if method != "GET" && method != "HEAD" {
        let _ = stream.write_all(b"HTTP/1.1 405 Method Not Allowed\r\nConnection: close\r\n\r\n");
        return;
    }
    let Some(file) = safe_join(root, path) else {
        let body = b"not found";
        let _ = write!(
            stream,
            "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        );
        let _ = stream.write_all(body);
        return;
    };
    let Ok(data) = fs::read(&file) else {
        let _ = stream.write_all(b"HTTP/1.1 500 Internal Server Error\r\nConnection: close\r\n\r\n");
        return;
    };
    let mime = mime_for(&file);
    let _ = write!(
        stream,
        "HTTP/1.1 200 OK\r\nContent-Type: {mime}\r\nContent-Length: {}\r\nCache-Control: no-cache\r\nConnection: close\r\n\r\n",
        data.len()
    );
    if method == "GET" {
        let _ = stream.write_all(&data);
    }
}

/// Bind once on `127.0.0.1:8767`. Fails loudly if the port is taken.
pub fn ensure_console_server() -> Result<u16, String> {
    if STARTED.get().is_some() {
        return Ok(CONSOLE_PORT);
    }
    let root = console_root()?;
    let listener = TcpListener::bind(("127.0.0.1", CONSOLE_PORT)).map_err(|e| {
        format!("console static bind 127.0.0.1:{CONSOLE_PORT} failed: {e} (is another pet running?)")
    })?;
    let root_for_thread = root.clone();
    thread::Builder::new()
        .name("console-static".into())
        .spawn(move || {
            for stream in listener.incoming().flatten() {
                let root = root_for_thread.clone();
                thread::spawn(move || handle_client(stream, &root));
            }
        })
        .map_err(|e| e.to_string())?;
    let _ = STARTED.set(());
    eprintln!("[pet] console UI http://127.0.0.1:{CONSOLE_PORT}/ (loopback Dist only)");
    Ok(CONSOLE_PORT)
}

pub fn console_index_url() -> String {
    format!("http://127.0.0.1:{CONSOLE_PORT}/index.html")
}
