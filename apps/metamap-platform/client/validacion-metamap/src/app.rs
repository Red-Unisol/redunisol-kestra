use std::{
    collections::{HashMap, HashSet},
    sync::{
        Arc,
        mpsc::{self, Receiver, Sender},
    },
    thread,
    time::{Duration, Instant},
};

use anyhow::Result;
use chrono::{DateTime, Local};
use eframe::egui::{self, Color32, RichText};

use crate::{
    APP_NAME_WITH_TAG,
    config::AppConfig,
    core_client::CoreClient,
    models::{CoreSnapshot, MonitorItem, SnapshotSummary, ValidationSnapshot, normalize_digits},
    notifications,
    server_client::ServerClient,
};

const PAGE_SIZE: usize = 200;

pub struct ValidacionMetamapApp {
    services: Arc<AppServices>,
    items: Vec<MonitorItem>,
    summary: SnapshotSummary,
    warnings: Vec<String>,
    last_updated_at: Option<DateTime<Local>>,
    next_poll_at: Instant,
    items_loading: bool,
    has_seeded: bool,
    notices: Vec<String>,
    event_tx: Sender<WorkerEvent>,
    event_rx: Receiver<WorkerEvent>,
}

struct AppServices {
    server: ServerClient,
    core: CoreClient,
    poll_interval: Duration,
    max_items: usize,
}

struct SnapshotPayload {
    items: Vec<MonitorItem>,
    summary: SnapshotSummary,
    warnings: Vec<String>,
    fetched_at: DateTime<Local>,
}

enum WorkerEvent {
    SnapshotLoaded(SnapshotPayload),
    SnapshotFailed(String),
}

impl ValidacionMetamapApp {
    pub fn new(config: AppConfig) -> Result<Self> {
        let services = Arc::new(AppServices::new(config)?);
        let (event_tx, event_rx) = mpsc::channel();
        let mut app = Self {
            services,
            items: Vec::new(),
            summary: SnapshotSummary::default(),
            warnings: Vec::new(),
            last_updated_at: None,
            next_poll_at: Instant::now(),
            items_loading: false,
            has_seeded: false,
            notices: Vec::new(),
            event_tx,
            event_rx,
        };
        app.spawn_refresh();
        Ok(app)
    }

    fn spawn_refresh(&mut self) {
        if self.items_loading {
            return;
        }

        self.items_loading = true;
        let services = Arc::clone(&self.services);
        let sender = self.event_tx.clone();

        thread::spawn(move || match services.load_snapshot() {
            Ok(snapshot) => {
                let _ = sender.send(WorkerEvent::SnapshotLoaded(snapshot));
            }
            Err(error) => {
                let _ = sender.send(WorkerEvent::SnapshotFailed(error.to_string()));
            }
        });
    }

    fn process_worker_events(&mut self) {
        while let Ok(event) = self.event_rx.try_recv() {
            match event {
                WorkerEvent::SnapshotLoaded(snapshot) => {
                    self.items_loading = false;
                    self.next_poll_at = Instant::now() + self.services.poll_interval;
                    self.last_updated_at = Some(snapshot.fetched_at);
                    self.warnings = snapshot.warnings.clone();

                    if self.has_seeded {
                        let previous_ids = self
                            .items
                            .iter()
                            .map(|item| item.id.clone())
                            .collect::<HashSet<_>>();
                        let new_items = snapshot
                            .items
                            .iter()
                            .filter(|item| !previous_ids.contains(&item.id))
                            .cloned()
                            .collect::<Vec<_>>();

                        if !new_items.is_empty() {
                            emit_new_item_notifications(&new_items);
                            self.push_notice(format!(
                                "Entraron {} validacion{} nueva{}.",
                                new_items.len(),
                                if new_items.len() == 1 { "" } else { "es" },
                                if new_items.len() == 1 { "" } else { "s" }
                            ));
                        }
                    }

                    self.has_seeded = true;
                    self.summary = snapshot.summary;
                    self.items = snapshot.items;

                    if self.warnings.is_empty() {
                        self.push_notice("Monitor actualizado.");
                    } else {
                        self.push_notice(format!(
                            "Monitor actualizado con advertencias: {}",
                            self.warnings.join(" | ")
                        ));
                    }
                }
                WorkerEvent::SnapshotFailed(error) => {
                    self.items_loading = false;
                    self.next_poll_at = Instant::now() + self.services.poll_interval;
                    self.push_notice(format!("Error actualizando el monitor: {error}"));
                }
            }
        }
    }

    fn push_notice(&mut self, message: impl Into<String>) {
        let timestamp = Local::now().format("%H:%M:%S");
        self.notices
            .insert(0, format!("[{timestamp}] {}", message.into()));
        if self.notices.len() > 30 {
            self.notices.truncate(30);
        }
    }
}

impl eframe::App for ValidacionMetamapApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.process_worker_events();

        if !self.items_loading && Instant::now() >= self.next_poll_at {
            self.spawn_refresh();
        }

        egui::TopBottomPanel::top("toolbar").show(ctx, |ui| {
            ui.vertical(|ui| {
                ui.horizontal_wrapped(|ui| {
                    ui.heading(APP_NAME_WITH_TAG);
                    ui.separator();
                    ui.label(
                        RichText::new("Cliente local privado")
                            .color(Color32::from_rgb(34, 108, 62))
                            .strong(),
                    );
                    ui.separator();
                    ui.label(format!("Validaciones hoy: {}", self.summary.total));
                    ui.label(format!("Con datos del core: {}", self.summary.core_enriched));
                    ui.label(format!(
                        "Polling: {}s",
                        self.services.poll_interval.as_secs()
                    ));
                    if let Some(last_updated_at) = self.last_updated_at {
                        ui.label(format!(
                            "Ultima actualizacion: {}",
                            last_updated_at.format("%H:%M:%S")
                        ));
                    }
                    if ui
                        .add_enabled(!self.items_loading, egui::Button::new("Actualizar ahora"))
                        .clicked()
                    {
                        self.spawn_refresh();
                    }
                });

                if self.items_loading {
                    ui.label(RichText::new("Actualizando lista...").color(Color32::GRAY));
                }

                for warning in &self.warnings {
                    ui.label(RichText::new(warning).color(Color32::from_rgb(180, 108, 0)));
                }
            });
        });

        egui::TopBottomPanel::bottom("events")
            .resizable(true)
            .default_height(150.0)
            .show(ctx, |ui| {
                ui.heading("Eventos");
                egui::ScrollArea::vertical().show(ui, |ui| {
                    for notice in &self.notices {
                        ui.label(notice);
                    }
                });
            });

        egui::CentralPanel::default().show(ctx, |ui| {
            if self.items.is_empty() {
                ui.add_space(40.0);
                ui.vertical_centered(|ui| {
                    if self.items_loading {
                        ui.label(RichText::new("Leyendo validaciones del dia...").size(22.0));
                    } else {
                        ui.label(RichText::new("No hay validaciones completed registradas hoy.").size(22.0));
                    }
                });
                return;
            }

            egui::ScrollArea::vertical().show(ui, |ui| {
                let available_width = ui.available_width().max(360.0);
                let columns = ((available_width + 16.0) / 360.0).floor().max(1.0) as usize;
                let card_width = ((available_width - (16.0 * (columns.saturating_sub(1) as f32)))
                    / columns as f32)
                    .max(320.0);

                egui::Grid::new("validation_cards_grid")
                    .num_columns(columns)
                    .spacing([16.0, 16.0])
                    .show(ui, |ui| {
                        for (index, item) in self.items.iter().enumerate() {
                            ui.vertical(|ui| render_card(ui, item, card_width));

                            if (index + 1) % columns == 0 {
                                ui.end_row();
                            }
                        }
                    });
            });
        });

        ctx.request_repaint_after(Duration::from_millis(250));
    }
}

impl AppServices {
    fn new(config: AppConfig) -> Result<Self> {
        Ok(Self {
            server: ServerClient::new(&config.server, config.request_timeout)?,
            core: CoreClient::new(&config.core, config.request_timeout)?,
            poll_interval: config.poll_interval,
            max_items: config.max_items.max(PAGE_SIZE),
        })
    }

    fn load_snapshot(&self) -> Result<SnapshotPayload> {
        let today = Local::now().date_naive();
        let mut offset = 0usize;
        let mut validations = Vec::new();

        while offset < self.max_items {
            let limit = PAGE_SIZE.min(self.max_items - offset);
            let batch = self.server.list_completed_page(limit, offset)?;

            if batch.is_empty() {
                break;
            }

            for validation in &batch {
                if validation
                    .event_at()
                    .map(|event_at| event_at.with_timezone(&Local).date_naive() == today)
                    .unwrap_or(false)
                {
                    validations.push(validation.clone());
                }
            }

            if batch.len() < limit {
                break;
            }

            if let Some(last_timestamp) = batch.last().and_then(ValidationSnapshot::sort_at) {
                if last_timestamp.with_timezone(&Local).date_naive() < today {
                    break;
                }
            }

            offset += batch.len();
        }

        let request_numbers = validations
            .iter()
            .filter_map(ValidationSnapshot::request_number_trimmed)
            .collect::<Vec<_>>();

        let mut warnings = Vec::new();
        let core_snapshots = match self.core.fetch_request_snapshots(&request_numbers) {
            Ok(values) => values,
            Err(error) => {
                warnings.push(format!(
                    "No se pudo completar el enriquecimiento desde el core financiero: {error}"
                ));
                HashMap::new()
            }
        };

        let missing_documents = validations
            .iter()
            .filter_map(|validation| {
                let request_number = validation.request_number_trimmed()?;
                let core_snapshot = core_snapshots.get(&request_number);
                let has_cuil = core_snapshot
                    .and_then(|snapshot| snapshot.cuil.as_deref())
                    .map(str::trim)
                    .is_some_and(|value| !value.is_empty());
                if has_cuil {
                    return None;
                }

                core_snapshot
                    .and_then(|snapshot| snapshot.document_number.clone())
                    .or_else(|| validation.document_number_trimmed())
            })
            .collect::<Vec<_>>();

        let cuil_by_document = match self.core.fetch_cuil_by_documents(&missing_documents) {
            Ok(values) => values,
            Err(error) => {
                if !missing_documents.is_empty() {
                    warnings.push(format!(
                        "No se pudo completar el CUIL desde SocioMutual: {error}"
                    ));
                }
                HashMap::new()
            }
        };

        let mut items = validations
            .iter()
            .map(|validation| build_monitor_item(validation, &core_snapshots, &cuil_by_document))
            .collect::<Vec<_>>();
        items.sort_by(|left, right| right.event_at.cmp(&left.event_at));

        let summary = SnapshotSummary {
            total: items.len(),
            core_enriched: items.iter().filter(|item| item.core_enriched).count(),
        };

        Ok(SnapshotPayload {
            items,
            summary,
            warnings,
            fetched_at: Local::now(),
        })
    }
}

fn build_monitor_item(
    validation: &ValidationSnapshot,
    core_snapshots: &HashMap<String, CoreSnapshot>,
    cuil_by_document: &HashMap<String, String>,
) -> MonitorItem {
    let request_number = validation
        .request_number_trimmed()
        .unwrap_or_else(|| "Sin solicitud".to_owned());
    let core_snapshot = core_snapshots.get(&request_number);
    let document_number = core_snapshot
        .and_then(|snapshot| snapshot.document_number.clone())
        .or_else(|| validation.document_number_trimmed());
    let document_digits = document_number
        .as_deref()
        .map(normalize_digits)
        .unwrap_or_default();

    let cuil = core_snapshot
        .and_then(|snapshot| snapshot.cuil.clone())
        .or_else(|| cuil_by_document.get(&document_digits).cloned())
        .unwrap_or_else(|| "Sin CUIL".to_owned());

    let name = core_snapshot
        .and_then(|snapshot| snapshot.name.clone())
        .or_else(|| validation.applicant_name.clone())
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "Sin nombre".to_owned());

    let line = core_snapshot
        .and_then(|snapshot| snapshot.line.clone())
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "Sin linea".to_owned());

    let amount = core_snapshot
        .and_then(|snapshot| snapshot.amount.clone())
        .or_else(|| validation.fallback_amount())
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "Sin monto".to_owned());

    let event_at = validation.event_at().map(|value| value.with_timezone(&Local));
    let event_label = event_at
        .map(|value| value.format("%d/%m %H:%M:%S").to_string())
        .unwrap_or_else(|| "Sin horario".to_owned());

    let core_enriched = core_snapshot
        .map(|snapshot| {
            snapshot.name.is_some()
                || snapshot.line.is_some()
                || snapshot.amount.is_some()
                || snapshot.cuil.is_some()
        })
        .unwrap_or(false);

    MonitorItem {
        id: validation.display_id(),
        verification_id: validation.verification_id.clone(),
        name,
        line,
        request_number,
        cuil,
        amount,
        event_at,
        event_label,
        core_enriched,
    }
}

fn emit_new_item_notifications(new_items: &[MonitorItem]) {
    if new_items.is_empty() {
        return;
    }

    if new_items.len() == 1 {
        let item = &new_items[0];
        let title = format!("Nueva validacion {}", item.request_number);
        let body = format!("{} | {} | {}", item.name, item.line, item.amount);
        notifications::notify(&title, &body);
        return;
    }

    let preview = new_items
        .iter()
        .take(2)
        .map(|item| format!("{} {}", item.request_number, item.name))
        .collect::<Vec<_>>()
        .join(" | ");
    notifications::notify(
        &format!("{} validaciones nuevas", new_items.len()),
        &preview,
    );
}

fn render_card(ui: &mut egui::Ui, item: &MonitorItem, card_width: f32) {
    ui.set_min_width(card_width);

    let frame = egui::Frame::group(ui.style());
    frame.show(ui, |ui| {
        ui.set_min_width(card_width - 12.0);
        ui.spacing_mut().item_spacing = egui::vec2(10.0, 10.0);

        ui.horizontal_wrapped(|ui| {
            ui.label(RichText::new(&item.event_label).color(Color32::GRAY).size(14.0));
            let source_text = if item.core_enriched {
                "Core + MetaMap"
            } else {
                "MetaMap"
            };
            let source_color = if item.core_enriched {
                Color32::from_rgb(24, 120, 52)
            } else {
                Color32::from_rgb(170, 110, 0)
            };
            ui.label(RichText::new(source_text).color(source_color).strong().size(14.0));
        });

        if let Some(verification_id) = item.verification_id.as_deref() {
            ui.label(RichText::new(verification_id).color(Color32::GRAY).size(13.0));
        }

        ui.label(RichText::new(&item.name).size(30.0).strong());
        ui.separator();

        render_metric(ui, "LINEA", &item.line, 22.0);
        render_metric(ui, "NUM SOLICITUD", &item.request_number, 22.0);
        render_metric(ui, "CUIL", &item.cuil, 22.0);
        render_metric(ui, "MONTO", &item.amount, 28.0);
    });
}

fn render_metric(ui: &mut egui::Ui, label: &str, value: &str, value_size: f32) {
    ui.label(RichText::new(label).size(13.0).color(Color32::GRAY).strong());
    ui.label(RichText::new(value).size(value_size).strong());
}
