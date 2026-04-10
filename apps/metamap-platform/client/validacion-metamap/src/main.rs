use anyhow::Result;
use validacion_metamap::{
    APP_NAME_WITH_TAG,
    app::ValidacionMetamapApp,
    config::AppConfig,
    logging,
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
        Box::new(move |_creation_context| Ok(Box::new(app))),
    )
}

fn load_runtime_config() -> Result<AppConfig> {
    AppConfig::load()
}
