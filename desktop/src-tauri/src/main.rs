// 유니버스 데스크톱 앱 껍데기 — 창·트레이만 맡고, 일은 로컬 서버 사이드카(univus-backend, PyInstaller)가 한다.
//
//   1. 시작 화면(splash)을 띄우고 사이드카를 `--exit-with-stdin` 으로 실행한다 (콘솔 창 없이).
//   2. 사이드카가 표준출력에 `UNIVUS_READY {"launchUrl": …}` 를 쓰면 창을 그 주소로 보낸다
//      → 서버가 한 번 쓰는 코드를 세션 쿠키로 바꿔 준다(univ_us_local/backend/app/main.py). 다른 프로그램은 API 를 못 부른다.
//   3. 창을 닫으면 트레이로 숨는다(예약 수집·마감 알림이 계속 돈다). 트레이 메뉴: 열기 · 로그인할 때 실행 · 종료.
//   4. 종료하면 사이드카의 표준입력을 닫아 스스로 끝나게 하고, 5초 안에 안 끝나면 강제로 끝낸다.
//   학교 사이트 등 바깥 주소는 앱 창이 아니라 기본 브라우저로 연다. 대시보드(127.0.0.1)에는 Tauri API 를 열지 않는다.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::webview::NewWindowResponse;
use tauri::window::Color;
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_opener::OpenerExt;

const READY_PREFIX: &str = "UNIVUS_READY ";
// 디자인 v3 "Paper & Pine" 바탕색 (univ_us_local/frontend/DESIGN.md) — 종이 #F8F4F0 (다크 모드 없음)
const PAPER: Color = Color(0xf8, 0xf4, 0xf0, 0xff);
const HIDDEN_ARG: &str = "--hidden"; // 로그인할 때 자동 실행이면 창 없이 트레이로만

struct Sidecar(Mutex<Option<Child>>);

/// 사이드카를 띄울 명령 — 설치본은 resources/sidecar/ 의 실행 파일.
/// 디버그 빌드(`npm run dev` = tauri dev)는 저장소 소스를 desktop/sidecar/.venv(사이드카 빌드와 같은 venv)의 python 으로 바로 띄운다.
/// UNIVUS_SIDECAR=<실행 파일> 이면 그것을 쓴다 — 묶은 사이드카(desktop/sidecar/dist)를 dev 껍데기로 시험할 때.
fn sidecar_command(app: &AppHandle) -> Result<Command, String> {
    if let Ok(p) = std::env::var("UNIVUS_SIDECAR") {
        return Ok(exe_command(PathBuf::from(p)));
    }
    if cfg!(debug_assertions) {
        return dev_command();
    }
    let exe = if cfg!(windows) { "univus-backend.exe" } else { "univus-backend" };
    match app.path().resource_dir() {
        Ok(dir) if dir.join("sidecar").join(exe).exists() => Ok(exe_command(dir.join("sidecar").join(exe))),
        _ => Err("로컬 서버 실행 파일을 찾지 못했습니다 — 앱을 다시 설치해 주세요".into()),
    }
}

fn exe_command(path: PathBuf) -> Command {
    let mut cmd = Command::new(&path);
    if let Some(dir) = path.parent() {
        cmd.current_dir(dir);
    }
    cmd
}

// 개발 모드 — next dev(화면 즉시 반영)는 tauri.dev.conf.json 의 beforeDevCommand 가 띄우고, 백엔드는 이 포트에 고정한다
// (next.config.ts 의 BACKEND_URL 기본값과 같아야 한다). 데이터는 설치된 앱과 따로 desktop/.dev-data.
const DEV_BACKEND_PORT: &str = "8020";
const DEV_FRONTEND_URL: &str = "http://127.0.0.1:3000";

fn dev_command() -> Result<Command, String> {
    let desktop = PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().map(PathBuf::from).unwrap_or_default();
    let repo = desktop.parent().map(PathBuf::from).unwrap_or_default();
    let backend = repo.join("univ_us_local").join("backend");
    let venv = desktop.join("sidecar").join(".venv");
    let py = if cfg!(windows) { venv.join("Scripts").join("python.exe") } else { venv.join("bin").join("python") };
    if !py.exists() {
        return Err(format!("개발 모드: {} 이(가) 없습니다 — desktop/README.md 의 개발 준비를 먼저 하세요", py.display()));
    }
    let mut cmd = Command::new(py);
    cmd.current_dir(&backend)
        .args(["-X", "utf8", "desktop.py", "--dev", "--port", DEV_BACKEND_PORT, "--frontend-url", DEV_FRONTEND_URL])
        .arg("--data-root")
        .arg(desktop.join(".dev-data"));
    Ok(cmd)
}

/// 시작 화면의 안내 문구를 바꾼다 (대시보드로 넘어간 뒤에는 #msg 가 없어 아무 일도 없다)
fn show_status(app: &AppHandle, msg: &str) {
    if let Some(w) = app.get_webview_window("main") {
        let text = serde_json::to_string(msg).unwrap_or_default();
        let _ = w.eval(&format!("var m=document.getElementById('msg'); if (m) m.textContent = {text};"));
    }
}

fn start_sidecar(app: &AppHandle) {
    let mut cmd = match sidecar_command(app) {
        Ok(c) => c,
        Err(msg) => {
            show_status(app, &msg);
            return;
        }
    };
    // 개발 모드는 서버 로그를 tauri dev 터미널에 그대로 보인다 (설치본은 앱 데이터 폴더/logs/backend.log)
    let stderr = if cfg!(debug_assertions) { Stdio::inherit() } else { Stdio::null() };
    cmd.arg("--exit-with-stdin").stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(stderr);
    #[cfg(all(windows, not(debug_assertions)))]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW — 콘솔 창을 띄우지 않는다 (디버그 빌드는 tauri dev 콘솔을 같이 쓴다)
    }
    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            show_status(app, &format!("로컬 서버를 시작하지 못했습니다: {e}"));
            return;
        }
    };
    let stdout = child.stdout.take();
    app.state::<Sidecar>().0.lock().unwrap().replace(child);

    let handle = app.clone();
    std::thread::spawn(move || {
        let Some(out) = stdout else { return };
        for line in BufReader::new(out).lines().map_while(Result::ok) {
            let Some(json) = line.strip_prefix(READY_PREFIX) else { continue };
            let url = serde_json::from_str::<serde_json::Value>(json)
                .ok()
                .and_then(|v| v["launchUrl"].as_str().and_then(|s| Url::parse(s).ok()));
            match (url, handle.get_webview_window("main")) {
                (Some(u), Some(w)) => {
                    let _ = w.navigate(u);
                }
                _ => show_status(&handle, "로컬 서버 응답을 읽지 못했습니다"),
            }
        }
        // 표준출력이 닫혔다 = 서버가 끝났다 (앱을 끝내는 중이면 창이 이미 없다)
        show_status(&handle, "로컬 서버가 멈췄습니다 — 트레이에서 종료한 뒤 다시 실행해 주세요 (로그: 앱 데이터 폴더/logs)");
    });
}

fn stop_sidecar(app: &AppHandle) {
    let Some(mut child) = app.state::<Sidecar>().0.lock().unwrap().take() else { return };
    drop(child.stdin.take()); // 표준입력을 닫으면 사이드카가 스스로 끝난다 (--exit-with-stdin)
    for _ in 0..50 {
        if let Ok(Some(_)) = child.try_wait() {
            return;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    let _ = child.kill();
}

fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

/// 앱 창 안에서 열어도 되는 주소 — 시작 화면(tauri://, http://tauri.localhost)과 로컬 서버(127.0.0.1)
fn is_local(url: &Url) -> bool {
    matches!(url.scheme(), "tauri" | "about" | "data")
        || matches!(url.host_str(), Some("127.0.0.1") | Some("localhost") | Some("tauri.localhost"))
}

fn open_outside(app: &AppHandle, url: &Url) {
    if matches!(url.scheme(), "http" | "https" | "mailto") {
        let _ = app.opener().open_url(url.as_str(), None::<&str>);
    }
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "유니버스 열기", true, None::<&str>)?;
    let on_login = app.autolaunch().is_enabled().unwrap_or(false);
    let autostart = CheckMenuItem::with_id(app, "autostart", "로그인할 때 실행", true, on_login, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &autostart, &PredefinedMenuItem::separator(app)?, &quit])?;
    let check = autostart.clone();
    TrayIconBuilder::with_id("main")
        .icon(app.default_window_icon().cloned().expect("앱 아이콘"))
        .tooltip("유니버스")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, ev| match ev.id().as_ref() {
            "open" => show_main(app),
            "autostart" => {
                let want = check.is_checked().unwrap_or(false);
                let al = app.autolaunch();
                let _ = if want { al.enable() } else { al.disable() };
                let _ = check.set_checked(al.is_enabled().unwrap_or(false));
            }
            "quit" => {
                stop_sidecar(app);
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, ev| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = ev {
                show_main(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

fn main() {
    let app = tauri::Builder::default()
        // 두 번째로 실행하면 새로 띄우지 않고 떠 있는 창을 앞으로 (사이드카가 둘이 되지 않게) — 맨 먼저 등록해야 한다
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, Some(vec![HIDDEN_ARG])))
        .plugin(tauri_plugin_opener::init())
        .manage(Sidecar(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            let nav = handle.clone();
            let popup = handle.clone();
            let hidden = std::env::args().any(|a| a == HIDDEN_ARG);
            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("유니버스")
                .inner_size(1280.0, 860.0)
                .min_inner_size(960.0, 640.0)
                // 창 바탕 = 디자인 v3 종이색 — 시작 화면 → 대시보드로 넘어갈 때 흰색이 번쩍이지 않게
                .background_color(PAPER)
                .visible(!hidden)
                .on_navigation(move |url| {
                    if is_local(url) {
                        return true;
                    }
                    open_outside(&nav, url); // 학교 사이트 등은 기본 브라우저로
                    false
                })
                .on_new_window(move |url, _features| {
                    // target="_blank" — 로컬 서버(강의자료 원문 등)는 앱 창으로(세션 쿠키 공유), 바깥 주소는 기본 브라우저로
                    if is_local(&url) {
                        NewWindowResponse::Allow
                    } else {
                        open_outside(&popup, &url);
                        NewWindowResponse::Deny
                    }
                })
                .build()?;
            build_tray(&handle)?;
            start_sidecar(&handle);
            Ok(())
        })
        .on_window_event(|window, event| {
            // 창을 닫으면 끝내지 않고 트레이로 — 예약 수집·마감 알림은 계속 돈다
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("유니버스 앱을 시작하지 못했습니다");

    app.run(|app, event| match event {
        RunEvent::Exit => stop_sidecar(app),
        #[cfg(target_os = "macos")]
        RunEvent::Reopen { .. } => show_main(app),
        _ => {}
    });
}
