use std::sync::{Arc, Mutex};

use anyhow::{Result, anyhow};
use eframe::egui::{self, Key, RichText, TextEdit, ViewportCommand};
use transferencias_celesol::{
    app::TransferenciasApp,
    config::{self, AppConfig},
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

    let app = match TransferenciasApp::new(config) {
        Ok(app) => app,
        Err(error) => {
            log::error!("No se pudo iniciar la app: {error:#}");
            eprintln!("No se pudo iniciar la app: {error}");
            std::process::exit(1);
        }
    };

    let native_options = eframe::NativeOptions {
        viewport: eframe::egui::ViewportBuilder::default()
            .with_title("Transferencias Celesol")
            .with_inner_size([1500.0, 920.0])
            .with_min_inner_size([1200.0, 700.0]),
        ..Default::default()
    };

    eframe::run_native(
        "Transferencias Celesol",
        native_options,
        Box::new(move |_creation_context| Ok(Box::new(app))),
    )
}

fn load_runtime_config() -> Result<AppConfig> {
    let config_path = config::resolve_runtime_config_path()?;
    let Some(config_path) = config_path.as_deref() else {
        return AppConfig::load();
    };

    if cfg!(debug_assertions) || !config::is_encrypted_config_path(config_path) {
        return AppConfig::load();
    }

    if std::env::var_os("TRANSFERENCIAS_CONFIG_PASSPHRASE").is_some() {
        match AppConfig::load() {
            Ok(config) => return Ok(config),
            Err(error) if !is_passphrase_related_error(&error) => return Err(error),
            Err(error) => {
                log::warn!(
                    "La passphrase provista por entorno no permitio abrir la configuracion: {error:#}"
                );
            }
        }
    }

    let mut last_error = None;
    loop {
        let mut passphrase = prompt_for_passphrase(last_error.as_deref())?
            .ok_or_else(|| anyhow!("Se cancelo el ingreso de la passphrase de configuracion."))?;
        let result = AppConfig::load_with_passphrase(Some(passphrase.as_str()));
        passphrase.clear();

        match result {
            Ok(config) => return Ok(config),
            Err(error) if is_passphrase_related_error(&error) => {
                last_error = Some("Passphrase invalida. Volve a intentarlo.".to_owned());
            }
            Err(error) => return Err(error),
        }
    }
}

fn is_passphrase_related_error(error: &anyhow::Error) -> bool {
    error.chain().any(|cause| {
        let message = cause.to_string().to_ascii_lowercase();
        message.contains("passphrase")
            || message.contains("desencript")
            || message.contains("cifrado corrupto")
    })
}

fn prompt_for_passphrase(error_message: Option<&str>) -> Result<Option<String>> {
    let shared_state = Arc::new(Mutex::new(PassphrasePromptState::default()));
    let state_for_app = Arc::clone(&shared_state);
    let error_message = error_message.map(str::to_owned);

    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("Passphrase de configuración")
            .with_inner_size([420.0, 180.0])
            .with_resizable(false),
        ..Default::default()
    };

    eframe::run_native(
        "Passphrase de configuración",
        native_options,
        Box::new(move |_creation_context| {
            Ok(Box::new(PassphrasePromptApp {
                passphrase: String::new(),
                error_message,
                shared_state: state_for_app,
            }))
        }),
    )
    .map_err(|error| anyhow!("No se pudo abrir el prompt de passphrase: {error}"))?;

    let state = shared_state
        .lock()
        .map_err(|_| anyhow!("No se pudo recuperar el resultado del prompt de passphrase."))?;
    Ok(state.passphrase.clone())
}

#[derive(Default)]
struct PassphrasePromptState {
    passphrase: Option<String>,
}

struct PassphrasePromptApp {
    passphrase: String,
    error_message: Option<String>,
    shared_state: Arc<Mutex<PassphrasePromptState>>,
}

impl eframe::App for PassphrasePromptApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.vertical_centered(|ui| {
                ui.add_space(8.0);
                ui.heading("Configuración cifrada");
                ui.label("Ingresá la passphrase para abrir transferencias.env.enc");
                if let Some(error_message) = self.error_message.as_deref() {
                    ui.add_space(6.0);
                    ui.label(RichText::new(error_message).color(egui::Color32::RED));
                }
                ui.add_space(10.0);

                let response = ui.add_sized(
                    [320.0, 28.0],
                    TextEdit::singleline(&mut self.passphrase)
                        .password(true)
                        .hint_text("Passphrase"),
                );

                let submit =
                    response.lost_focus() && ui.input(|input| input.key_pressed(Key::Enter));
                ui.add_space(10.0);

                ui.horizontal(|ui| {
                    if ui.button("Cancelar").clicked() {
                        ctx.send_viewport_cmd(ViewportCommand::Close);
                    }
                    if ui
                        .add_enabled(
                            !self.passphrase.trim().is_empty(),
                            egui::Button::new("Desbloquear"),
                        )
                        .clicked()
                        || submit
                    {
                        if let Ok(mut state) = self.shared_state.lock() {
                            state.passphrase = Some(self.passphrase.clone());
                        }
                        self.passphrase.clear();
                        ctx.send_viewport_cmd(ViewportCommand::Close);
                    }
                });
            });
        });
    }
}
