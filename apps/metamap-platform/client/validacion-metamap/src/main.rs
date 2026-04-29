#![cfg_attr(
    all(target_os = "windows", not(debug_assertions)),
    windows_subsystem = "windows"
)]

use anyhow::Result;
use validacion_metamap::{
    APP_NAME_WITH_TAG, app::ValidacionMetamapApp, config::AppConfig, logging,
};

fn main() -> eframe::Result<()> {
    if let Err(error) = logging::init_logging() {
        eprintln!("No se pudo inicializar logging: {error}");
    }

    let config = match load_runtime_config() {
        Ok(config) => config,
        Err(error) => {
            log::error!("Error de configuracion: {error:#}");
            eprintln!("Error de configuracion: {error}");
            std::process::exit(1);
        }
    };

    let app = match ValidacionMetamapApp::new(config) {
        Ok(app) => app,
        Err(error) => {
            log::error!("No se pudo iniciar la app: {error:#}");
            eprintln!("No se pudo iniciar la app: {error}");
            std::process::exit(1);
        }
    };

    let native_options = eframe::NativeOptions {
        viewport: eframe::egui::ViewportBuilder::default()
            .with_title(APP_NAME_WITH_TAG)
            .with_inner_size([1540.0, 940.0])
            .with_min_inner_size([1180.0, 720.0]),
        ..Default::default()
    };

    eframe::run_native(
        APP_NAME_WITH_TAG,
        native_options,
        Box::new(move |creation_context| {
            configure_egui(&creation_context.egui_ctx);
            Ok(Box::new(app))
        }),
    )
}

fn load_runtime_config() -> Result<AppConfig> {
    AppConfig::load()
}

fn configure_egui(ctx: &eframe::egui::Context) {
    let mut visuals = eframe::egui::Visuals::light();
    visuals.panel_fill = eframe::egui::Color32::from_rgb(246, 248, 250);
    visuals.window_fill = eframe::egui::Color32::from_rgb(250, 251, 252);
    visuals.extreme_bg_color = eframe::egui::Color32::from_rgb(255, 255, 255);
    visuals.faint_bg_color = eframe::egui::Color32::from_rgb(238, 241, 244);
    visuals.widgets.noninteractive.bg_fill = eframe::egui::Color32::from_rgb(246, 248, 250);
    visuals.widgets.inactive.bg_fill = eframe::egui::Color32::from_rgb(255, 255, 255);
    visuals.widgets.hovered.bg_fill = eframe::egui::Color32::from_rgb(240, 244, 247);
    visuals.widgets.active.bg_fill = eframe::egui::Color32::from_rgb(228, 236, 243);

    ctx.set_theme(eframe::egui::Theme::Light);
    ctx.set_visuals(visuals);
}
