// 유니버스 데스크톱 앱 껍데기 — 창·트레이만 맡고, 일은 로컬 서버 사이드카(univus-backend, PyInstaller)가 한다.
//
//   1. 시작 화면(splash)을 띄우고 사이드카를 `--exit-with-stdin` 으로 실행한다 (콘솔 창 없이).
//   2. 사이드카가 표준출력에 `UNIVUS_READY {"launchUrl": …}` 를 쓰면 창을 그 주소로 보낸다
//      → 서버가 한 번 쓰는 코드를 세션 쿠키로 바꿔 준다(univ_us_local/backend/app/main.py). 다른 프로그램은 API 를 못 부른다.
//   3. 창을 닫으면 트레이로 숨는다(예약 수집·마감 알림이 계속 돈다). 트레이 메뉴: 열기 · 로그인할 때 실행 · 종료.
//   4. 종료하면 사이드카의 표준입력을 닫아 스스로 끝나게 하고, 5초 안에 안 끝나면 강제로 끝낸다.
//   5. 사이드카가 뜻밖에 끝나면 시작 화면으로 돌아가 다시 띄우고, 준비되면 보던 화면으로 돌아간다.
//      종료 코드는 새 사이드카가 backend.log 에 적는다. 10분 안에 세 번 넘게 끝나면 그만두고 시작 화면에 알린다.
//      (2026-11-11: 사이드카만 조용히 사라져 창이 127.0.0.1 연결 거부로 남았고, 로그에 언제·왜가 없었다)
//   학교 사이트 등 바깥 주소는 앱 창이 아니라 기본 브라우저로 연다. 대시보드(127.0.0.1)에는 Tauri API 를 열지 않는다.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

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

// 뜻밖에 끝난 사이드카를 다시 띄우는 한도 — 이 시간 안에 이만큼 넘게 끝나면 고장으로 보고 그만둔다
const RESTART_WINDOW: Duration = Duration::from_secs(10 * 60);
const MAX_RESTARTS: usize = 3;

#[derive(Default)]
struct Sidecar {
    child: Mutex<Option<Child>>,
    quitting: AtomicBool,                // 트레이 '종료'·앱 끝 — 이때 사이드카가 끝나는 것은 정상
    restarts: Mutex<Vec<Instant>>,       // 최근 다시 띄운 시각 (RESTART_WINDOW 안의 것만 남긴다)
    splash: Mutex<Option<Url>>,          // 시작 화면 주소 (첫 준비 줄 때 창이 보고 있던 주소)
    resume: Mutex<Option<String>>,       // 다시 띄운 뒤 돌아갈 대시보드 경로 (/exams?tab=… 등)
}

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

/// 사이드카를 띄운다. `restart_note` 가 있으면 다시 띄우는 것 — 새 사이드카가 그 사연(앞 서버의 종료 코드)을 로그에 적는다.
fn start_sidecar(app: &AppHandle, restart_note: Option<String>) -> Result<(), String> {
    let mut cmd = sidecar_command(app)?;
    // 개발 모드는 서버 로그를 tauri dev 터미널에 그대로 보인다 (설치본은 앱 데이터 폴더/logs/backend.log)
    let stderr = if cfg!(debug_assertions) { Stdio::inherit() } else { Stdio::null() };
    cmd.arg("--exit-with-stdin").stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(stderr);
    if let Some(note) = restart_note {
        cmd.env("UNIVUS_RESTART_NOTE", note);
    }
    #[cfg(all(windows, not(debug_assertions)))]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW — 콘솔 창을 띄우지 않는다 (디버그 빌드는 tauri dev 콘솔을 같이 쓴다)
    }
    let mut child = cmd.spawn().map_err(|e| format!("로컬 서버를 시작하지 못했습니다: {e}"))?;
    let pid = child.id();
    let stdout = child.stdout.take();
    app.state::<Sidecar>().child.lock().unwrap().replace(child);

    let handle = app.clone();
    std::thread::spawn(move || {
        let Some(out) = stdout else { return };
        for line in BufReader::new(out).lines().map_while(Result::ok) {
            let Some(json) = line.strip_prefix(READY_PREFIX) else { continue };
            let url = serde_json::from_str::<serde_json::Value>(json)
                .ok()
                .and_then(|v| v["launchUrl"].as_str().and_then(|s| Url::parse(s).ok()));
            match (url, handle.get_webview_window("main")) {
                (Some(mut u), Some(w)) => {
                    let st = handle.state::<Sidecar>();
                    // 시작 화면 주소는 처음 준비될 때 창에서 읽는다 — 창을 만든 직후에는 아직 about:blank 다 (2026-11-11 실측)
                    let mut splash = st.splash.lock().unwrap();
                    if splash.is_none() {
                        *splash = w.url().ok().filter(|s| s.scheme() != "about");
                    }
                    drop(splash);
                    // 다시 띄운 것이면 보던 화면으로 (서버의 /desktop/launch 가 같은 주소 안 경로만 받는다)
                    if let Some(next) = st.resume.lock().unwrap().take() {
                        u.query_pairs_mut().append_pair("next", &next);
                    }
                    let _ = w.navigate(u);
                }
                _ => show_status(&handle, "로컬 서버 응답을 읽지 못했습니다"),
            }
        }
    });

    // 끝났는지는 표준출력 EOF 가 아니라 프로세스로 본다 — 사이드카가 띄운 자식(수집기·로그인 창)이
    // 표준출력 핸들을 물려받아 살아 있으면 사이드카가 죽어도 EOF 가 오지 않는다
    let handle = app.clone();
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_secs(1));
        let status = {
            let st = handle.state::<Sidecar>();
            let mut slot = st.child.lock().unwrap();
            match slot.as_mut() {
                Some(c) if c.id() == pid => match c.try_wait() {
                    Ok(None) => continue,
                    Ok(Some(s)) => {
                        slot.take();
                        Ok(s)
                    }
                    Err(e) => {
                        slot.take();
                        Err(e)
                    }
                },
                _ => return, // stop_sidecar 가 가져갔다(앱 종료) — 또는 이미 새 사이드카로 바뀌었다
            }
        };
        on_sidecar_exit(&handle, status);
        return;
    });
    Ok(())
}

/// 사이드카가 끝났다 — 앱을 끝내는 중이 아니면 뜻밖의 종료이므로 다시 띄운다.
fn on_sidecar_exit(app: &AppHandle, status: std::io::Result<ExitStatus>) {
    let st = app.state::<Sidecar>();
    if st.quitting.load(Ordering::SeqCst) {
        return;
    }
    let code = exit_code(status);

    // 보던 대시보드 화면을 기억하고 시작 화면으로 — 죽은 서버 주소의 '연결 거부' 화면에 남지 않게
    if let Some(w) = app.get_webview_window("main") {
        let splash = st.splash.lock().unwrap().clone();
        if let Some(path) = w.url().ok().and_then(|u| dashboard_path(&u, splash.as_ref())) {
            st.resume.lock().unwrap().replace(path);
        }
    }
    let now = Instant::now();
    let allowed = {
        let mut times = st.restarts.lock().unwrap();
        times.retain(|t| now.duration_since(*t) < RESTART_WINDOW);
        let ok = times.len() < MAX_RESTARTS;
        if ok {
            times.push(now);
        }
        ok
    };
    if !allowed {
        show_splash(app, Some(&format!(
            "로컬 서버가 계속 멈춥니다 (종료 코드 {code}) — 트레이에서 종료한 뒤 다시 실행해 주세요 (로그: 앱 데이터 폴더/logs/backend.log)"
        )));
        return;
    }
    show_splash(app, None);
    std::thread::sleep(Duration::from_secs(1)); // 바로 다시 죽는 경우에 빈틈 없이 도는 것을 막는다
    if st.quitting.load(Ordering::SeqCst) {
        return;
    }
    if let Err(msg) = start_sidecar(app, Some(format!("앞 서버가 종료 코드 {code} 로 끝나서 앱이 다시 띄움"))) {
        show_splash(app, Some(&msg));
    }
}

/// 종료 코드 글자 — Windows 는 NTSTATUS 처럼 16진수(0xC000013A = Ctrl+C·콘솔 닫힘, 0xC0000005 = 메모리 접근 위반)
fn exit_code(status: std::io::Result<ExitStatus>) -> String {
    match status {
        Ok(s) => match s.code() {
            Some(c) if cfg!(windows) => format!("{:#010X}", c as u32),
            Some(c) => c.to_string(),
            None => s.to_string(), // 유닉스 신호
        },
        Err(e) => format!("알 수 없음({e})"),
    }
}

/// 대시보드(로컬 서버) 주소이면 경로+쿼리 — 시작 화면·실행 코드 주소는 돌아갈 곳이 아니다
/// (개발 모드의 시작 화면은 tauri dev 가 http://127.0.0.1:1430 에서 보여 주므로 주소의 출처로 가른다)
fn dashboard_path(url: &Url, splash: Option<&Url>) -> Option<String> {
    let local = matches!(url.scheme(), "http" | "https") && matches!(url.host_str(), Some("127.0.0.1") | Some("localhost"));
    let is_splash = splash.is_some_and(|s| s.origin() == url.origin());
    if !local || is_splash || url.path().starts_with("/desktop/") {
        return None;
    }
    Some(match url.query() {
        Some(q) => format!("{}?{q}", url.path()),
        None => url.path().to_string(),
    })
}

/// 창을 시작 화면으로 — error 가 없으면 '다시 시작하는 중', 있으면 오류 모양 (splash/index.html 이 쿼리를 읽는다)
fn show_splash(app: &AppHandle, error: Option<&str>) {
    // 처음 준비되기 전에 끝났으면 아직 모른다 — Tauri 2 의 앱 주소 (Windows http://tauri.localhost · 맥 tauri://localhost)
    let saved = app.state::<Sidecar>().splash.lock().unwrap().clone();
    let fallback = if cfg!(windows) { "http://tauri.localhost/index.html" } else { "tauri://localhost/index.html" };
    let Some(mut url) = saved.or_else(|| Url::parse(fallback).ok()) else { return };
    url.set_query(None);
    match error {
        Some(e) => url.query_pairs_mut().append_pair("error", e),
        None => url.query_pairs_mut().append_pair("restart", "1"),
    };
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.navigate(url);
    }
}

fn stop_sidecar(app: &AppHandle) {
    let st = app.state::<Sidecar>();
    st.quitting.store(true, Ordering::SeqCst); // 이제 끝나는 사이드카는 다시 띄우지 않는다
    let Some(mut child) = st.child.lock().unwrap().take() else { return };
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
        let res = app.opener().open_url(url.as_str(), None::<&str>);
        #[cfg(debug_assertions)]
        eprintln!("desktop: 바깥 링크 → 기본 브라우저 {url} ({res:?})"); // 개발 모드(tauri dev) 터미널에만
        let _ = res;
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
        // 링크 클릭 가로채기(open_js_links_on_click)는 끈다 — 그 스크립트는 target="_blank" 클릭을 막고 Tauri API(IPC)로 열려고 하는데,
        // 대시보드(127.0.0.1)에는 Tauri API 를 열지 않으므로 아무것도 열리지 않았다(e클래스·학사일정 '원문 보기', 2026-10-08).
        // 새 창 요청은 아래 on_new_window 가 받는다 — 바깥 주소는 기본 브라우저, 로컬 주소는 앱 창.
        .plugin(tauri_plugin_opener::Builder::new().open_js_links_on_click(false).build())
        .manage(Sidecar::default())
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
                // Tauri 의 파일 끌어놓기 처리를 끈다 — 켜 두면 Windows(WebView2)에서 화면의 HTML5 끌어놓기가 막혀
                // 강의자료(F4) '파일 끌어다 추가'가 브라우저와 달리 동작하지 않는다. Tauri 의 DragDropEvent 는 쓰지 않는다.
                .disable_drag_drop_handler()
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
                        #[cfg(debug_assertions)]
                        eprintln!("desktop: 새 앱 창 {url}");
                        NewWindowResponse::Allow
                    } else {
                        open_outside(&popup, &url);
                        NewWindowResponse::Deny
                    }
                })
                .build()?;
            build_tray(&handle)?;
            if let Err(msg) = start_sidecar(&handle, None) {
                show_status(&handle, &msg);
            }
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
