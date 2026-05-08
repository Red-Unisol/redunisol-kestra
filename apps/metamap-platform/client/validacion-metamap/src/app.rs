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
    media_downloader::MediaDownloader,
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
    hide_reviewed: bool,
    reviewing_ids: HashSet<String>,
    notices: Vec<String>,
    event_tx: Sender<WorkerEvent>,
    event_rx: Receiver<WorkerEvent>,
}

struct AppServices {
    server: ServerClient,
    core: CoreClient,
    media_downloader: Option<MediaDownloader>,
    poll_interval: Duration,
    max_items: usize,
}

struct SnapshotPayload {
    items: Vec<MonitorItem>,
    summary: SnapshotSummary,
    warnings: Vec<String>,
    downloaded_media_files: usize,
    downloaded_media_validations: usize,
    downloads_dir_display: Option<String>,
    fetched_at: DateTime<Local>,
}

enum WorkerEvent {
    SnapshotLoaded(SnapshotPayload),
    SnapshotFailed(String),
    ValidationReviewed(ValidationSnapshot),
    ValidationReviewFailed {
        verification_id: String,
        error: String,
    },
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
            hide_reviewed: false,
            reviewing_ids: HashSet::new(),
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

                    if snapshot.downloaded_media_validations > 0 {
                        let files_label = if snapshot.downloaded_media_files == 1 {
                            "archivo"
                        } else {
                            "archivos"
                        };
                        let validations_label = if snapshot.downloaded_media_validations == 1 {
                            "validacion"
                        } else {
                            "validaciones"
                        };
                        let target_label = snapshot
                            .downloads_dir_display
                            .as_deref()
                            .map(|path| format!(" en {path}"))
                            .unwrap_or_default();
                        self.push_notice(format!(
                            "Se descargaron {} {} de media para {} {}{}.",
                            snapshot.downloaded_media_files,
                            files_label,
                            snapshot.downloaded_media_validations,
                            validations_label,
                            target_label
                        ));
                    }

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
                WorkerEvent::ValidationReviewed(validation) => {
                    let Some(verification_id) = validation.verification_id_trimmed() else {
                        continue;
                    };
                    self.reviewing_ids.remove(&verification_id);

                    let reviewed_by = validation
                        .reviewed_by_display_name_trimmed()
                        .or_else(|| validation.reviewed_by_client_id_trimmed())
                        .unwrap_or_else(|| "cliente desconocido".to_owned());

                    let mut updated = false;
                    for item in &mut self.items {
                        if item.verification_id.as_deref() == Some(verification_id.as_str()) {
                            item.apply_review_state(&validation);
                            updated = true;
                            break;
                        }
                    }
                    if updated {
                        order_monitor_items(&mut self.items);
                        self.summary.reviewed = self.items.iter().filter(|item| item.is_reviewed()).count();
                    } else {
                        self.spawn_refresh();
                    }
                    self.push_notice(format!(
                        "Validacion {verification_id} marcada como revisada por {reviewed_by}."
                    ));
                }
                WorkerEvent::ValidationReviewFailed {
                    verification_id,
                    error,
                } => {
                    self.reviewing_ids.remove(&verification_id);
                    self.push_notice(format!(
                        "No se pudo marcar como revisada la validacion {verification_id}: {error}"
                    ));
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

    fn start_review(&mut self, verification_id: String) {
        if self.reviewing_ids.contains(&verification_id) {
            return;
        }

        self.reviewing_ids.insert(verification_id.clone());
        let services = Arc::clone(&self.services);
        let sender = self.event_tx.clone();

        thread::spawn(move || match services.mark_validation_reviewed(&verification_id) {
            Ok(validation) => {
                let _ = sender.send(WorkerEvent::ValidationReviewed(validation));
            }
            Err(error) => {
                let _ = sender.send(WorkerEvent::ValidationReviewFailed {
                    verification_id,
                    error: error.to_string(),
                });
            }
        });
    }
}

impl eframe::App for ValidacionMetamapApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.process_worker_events();

        if !self.items_loading && Instant::now() >= self.next_poll_at {
            self.spawn_refresh();
        }

        let mut clicked_review_id = None;

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
                    ui.label(format!("Revisadas: {}", self.summary.reviewed));
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
                    ui.checkbox(&mut self.hide_reviewed, "Ocultar revisadas");
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
            let visible_indices = self
                .items
                .iter()
                .enumerate()
                .filter(|(_, item)| !self.hide_reviewed || !item.is_reviewed())
                .map(|(index, _)| index)
                .collect::<Vec<_>>();

            if visible_indices.is_empty() {
                ui.add_space(40.0);
                ui.vertical_centered(|ui| {
                    if self.items_loading {
                        ui.label(RichText::new("Leyendo validaciones del dia...").size(22.0));
                    } else if self.hide_reviewed && !self.items.is_empty() {
                        ui.label(
                            RichText::new("No hay validaciones pendientes visibles.").size(22.0)
                        );
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
                        for (grid_index, item_index) in visible_indices.iter().enumerate() {
                            let item = &self.items[*item_index];
                            let reviewing = item
                                .verification_id
                                .as_deref()
                                .is_some_and(|verification_id| self.reviewing_ids.contains(verification_id));

                            ui.vertical(|ui| {
                                if render_card(ui, item, card_width, reviewing) {
                                    clicked_review_id = item.verification_id.clone();
                                }
                            });

                            if (grid_index + 1) % columns == 0 {
                                ui.end_row();
                            }
                        }
                    });
            });
        });

        if let Some(verification_id) = clicked_review_id {
            self.start_review(verification_id);
        }

        ctx.request_repaint_after(Duration::from_millis(250));
    }
}

impl AppServices {
    fn new(config: AppConfig) -> Result<Self> {
        Ok(Self {
            server: ServerClient::new(&config.server, config.request_timeout)?,
            core: CoreClient::new(&config.core, config.request_timeout)?,
            media_downloader: MediaDownloader::from_config(&config.media, config.request_timeout)?,
            poll_interval: config.poll_interval,
            max_items: config.max_items.max(PAGE_SIZE),
        })
    }

    fn mark_validation_reviewed(&self, verification_id: &str) -> Result<ValidationSnapshot> {
        self.server.mark_validation_reviewed(verification_id)
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
        order_monitor_items(&mut items);

        let summary = SnapshotSummary {
            total: items.len(),
            core_enriched: items.iter().filter(|item| item.core_enriched).count(),
            reviewed: items.iter().filter(|item| item.is_reviewed()).count(),
        };

        let mut downloaded_media_files = 0usize;
        let mut downloaded_media_validations = 0usize;
        let mut downloads_dir_display = None;
        if let Some(media_downloader) = &self.media_downloader {
            let media_outcome = media_downloader.download_snapshot_media(&validations);
            downloaded_media_files = media_outcome.downloaded_files;
            downloaded_media_validations = media_outcome.downloaded_validations;
            downloads_dir_display = Some(media_outcome.downloads_dir.display().to_string());
            warnings.extend(media_outcome.warnings);
        }

        Ok(SnapshotPayload {
            items,
            summary,
            warnings,
            downloaded_media_files,
            downloaded_media_validations,
            downloads_dir_display,
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

    let reviewed_at = validation.reviewed_at().map(|value| value.with_timezone(&Local));
    let reviewed_label = reviewed_at
        .map(|value| format!("Revisada {}", value.format("%d/%m %H:%M:%S")));

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
        reviewed_at,
        reviewed_label,
        reviewed_by_display_name: validation.reviewed_by_display_name_trimmed(),
        reviewed_by_client_id: validation.reviewed_by_client_id_trimmed(),
    }
}

fn order_monitor_items(items: &mut [MonitorItem]) {
    items.sort_by(|left, right| {
        left.is_reviewed()
            .cmp(&right.is_reviewed())
            .then_with(|| right.event_at.cmp(&left.event_at))
            .then_with(|| left.id.cmp(&right.id))
    });
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

fn render_card(ui: &mut egui::Ui, item: &MonitorItem, card_width: f32, reviewing: bool) -> bool {
    ui.set_min_width(card_width);

    let reviewed = item.is_reviewed();
    let frame = egui::Frame::group(ui.style()).fill(if reviewed {
        Color32::from_gray(242)
    } else {
        ui.visuals().extreme_bg_color
    });
    let mut mark_reviewed_clicked = false;

    frame.show(ui, |ui| {
        ui.set_min_width(card_width - 12.0);
        ui.spacing_mut().item_spacing = egui::vec2(10.0, 10.0);

        let primary_text_color = if reviewed {
            Color32::from_gray(110)
        } else {
            ui.visuals().text_color()
        };
        let secondary_text_color = if reviewed {
            Color32::from_gray(140)
        } else {
            Color32::GRAY
        };

        ui.horizontal_wrapped(|ui| {
            ui.label(RichText::new(&item.event_label).color(secondary_text_color).size(14.0));
            let source_text = if item.core_enriched {
                "Core + MetaMap"
            } else {
                "MetaMap"
            };
            let source_color = if item.core_enriched {
                if reviewed {
                    Color32::from_rgb(96, 132, 104)
                } else {
                    Color32::from_rgb(24, 120, 52)
                }
            } else {
                if reviewed {
                    Color32::from_rgb(156, 134, 90)
                } else {
                    Color32::from_rgb(170, 110, 0)
                }
            };
            ui.label(RichText::new(source_text).color(source_color).strong().size(14.0));
            if let Some(reviewed_label) = &item.reviewed_label {
                ui.label(RichText::new(reviewed_label).color(Color32::from_rgb(80, 110, 150)).size(14.0));
            }
        });

        if let Some(verification_id) = item.verification_id.as_deref() {
            ui.label(RichText::new(verification_id).color(secondary_text_color).size(13.0));
        }

        ui.label(RichText::new(&item.name).color(primary_text_color).size(30.0).strong());
        ui.separator();

        render_metric(ui, "LINEA", &item.line, 22.0, reviewed);
        render_metric(ui, "NUM SOLICITUD", &item.request_number, 22.0, reviewed);
        render_metric(ui, "CUIL", &item.cuil, 22.0, reviewed);
        render_metric(ui, "MONTO", &item.amount, 28.0, reviewed);

        if let Some(reviewed_by) = item
            .reviewed_by_display_name
            .as_deref()
            .or(item.reviewed_by_client_id.as_deref())
        {
            ui.label(
                RichText::new(format!("Marcada por {reviewed_by}"))
                    .color(secondary_text_color)
                    .size(13.0),
            );
        }

        if !reviewed && item.verification_id.is_some() {
            let button_label = if reviewing {
                "Marcando..."
            } else {
                "Marcar revisada"
            };
            if ui
                .add_enabled(!reviewing, egui::Button::new(button_label))
                .clicked()
            {
                mark_reviewed_clicked = true;
            }
        }
    });

    mark_reviewed_clicked
}

fn render_metric(ui: &mut egui::Ui, label: &str, value: &str, value_size: f32, reviewed: bool) {
    let label_color = if reviewed {
        Color32::from_gray(140)
    } else {
        Color32::GRAY
    };
    let value_color = if reviewed {
        Color32::from_gray(110)
    } else {
        ui.visuals().text_color()
    };
    ui.label(RichText::new(label).size(13.0).color(label_color).strong());
    ui.label(RichText::new(value).color(value_color).size(value_size).strong());
}
