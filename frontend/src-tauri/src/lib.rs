//! FreeTodo - Tauri Application Library
//!
//! This module contains the core functionality for the FreeTodo desktop application,
//! including backend management, Next.js server management, system tray, and global shortcuts.
//!
//! ## Window Modes
//!
//! The application supports two window modes (matching Electron implementation):
//! - **Web Mode**: Standard window with decorations
//! - **Island Mode**: Transparent floating window like Dynamic Island (separate build config)

pub mod backend;
mod backend_log;
mod backend_paths;
mod backend_proxy;
mod backend_python;
mod backend_support;
pub mod config;
pub mod nextjs;
pub mod shortcut;
pub mod tray;

use log::info;
use tauri::Manager;

/// Window mode configuration
/// Currently only Web mode is supported
#[derive(Debug, Clone, Copy, PartialEq, Default)]
#[allow(dead_code)]
pub enum WindowMode {
    /// Standard window with decorations (default, currently supported)
    #[default]
    Web,
    /// Transparent floating window like Dynamic Island (TODO: not yet implemented)
    Island,
}

/// Initialize the Tauri application with all required plugins and setup
/// Note: Currently only Web mode is supported
pub fn run() {
    // Initialize logger
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    info!("Starting FreeTodo application...");

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            let handle = app.handle().clone();

            info!("Application setup starting...");

            // Start Python backend
            let backend_handle = handle.clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = backend::start_backend(&backend_handle).await {
                    log::error!("Failed to start backend: {}", e);
                }
            });

            // Start Next.js server (only in release mode)
            #[cfg(not(debug_assertions))]
            {
                let nextjs_handle = handle.clone();
                tauri::async_runtime::spawn(async move {
                    if let Err(e) = nextjs::start_nextjs(&nextjs_handle).await {
                        log::error!("Failed to start Next.js: {}", e);
                    }
                });
            }

            // Setup system tray
            tray::setup_tray(app)?;

            // Setup global shortcuts
            shortcut::setup_shortcuts(app)?;

            info!("Application setup completed");

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_url,
            get_backend_status,
            toggle_window,
            show_window,
            hide_window,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// Get the backend server URL
#[tauri::command]
fn get_backend_url() -> String {
    backend::get_backend_url()
}

/// Get backend server health status
#[tauri::command]
async fn get_backend_status() -> Result<bool, String> {
    backend::check_backend_health(config::get_backend_port())
        .await
        .map_err(|e| e.to_string())
}

/// Toggle main window visibility
#[tauri::command]
fn toggle_window(app: tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
        } else {
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

/// Show main window
#[tauri::command]
fn show_window(app: tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

/// Hide main window
#[tauri::command]
fn hide_window(app: tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }
}
