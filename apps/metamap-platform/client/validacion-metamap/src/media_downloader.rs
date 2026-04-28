use std::{
    collections::HashSet,
    fs,
    path::PathBuf,
    time::Duration,
};

use anyhow::{Context, Result};
use chrono::Local;
use reqwest::{Url, blocking::Client};
use serde::Deserialize;
use serde_json::{Value, json};

use crate::{config::MediaConfig, models::ValidationSnapshot};

pub struct MediaBatchOutcome {
    pub downloaded_files: usize,
    pub downloaded_validations: usize,
    pub downloads_dir: PathBuf,
    pub warnings: Vec<String>,
}

#[derive(Clone)]
pub struct MediaDownloader {
    http: Client,
    downloads_dir: PathBuf,
    index_dir: PathBuf,
    metamap_client_id: String,
    metamap_client_secret: String,
}

struct ValidationDownloadOutcome {
    file_count: usize,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct MediaEntry {
    path: Vec<String>,
    url: String,
}

#[derive(Deserialize)]
struct OAuthTokenResponse {
    access_token: String,
}

impl MediaDownloader {
    pub fn from_config(config: &MediaConfig, timeout: Duration) -> Result<Option<Self>> {
        let Some(metamap_client_id) = config.metamap_client_id.clone() else {
            return Ok(None);
        };
        let Some(metamap_client_secret) = config.metamap_client_secret.clone() else {
            return Ok(None);
        };

        let http = Client::builder()
            .timeout(timeout)
            .build()
            .context("No se pudo construir el cliente HTTP de media MetaMap.")?;

        let downloads_dir = config.downloads_dir.clone();
        let index_dir = downloads_dir.join("_download-index");

        Ok(Some(Self {
            http,
            downloads_dir,
            index_dir,
            metamap_client_id,
            metamap_client_secret,
        }))
    }

    pub fn download_snapshot_media(&self, validations: &[ValidationSnapshot]) -> MediaBatchOutcome {
        let mut downloaded_files = 0usize;
        let mut downloaded_validations = 0usize;
        let mut warnings = Vec::new();

        if let Err(error) = fs::create_dir_all(&self.index_dir) {
            warnings.push(format!(
                "No se pudo preparar la carpeta de descargas de media {:?}: {error}",
                self.downloads_dir
            ));
            return MediaBatchOutcome {
                downloaded_files,
                downloaded_validations,
                downloads_dir: self.downloads_dir.clone(),
                warnings,
            };
        }

        for validation in validations {
            match self.download_validation_media(validation) {
                Ok(Some(outcome)) => {
                    downloaded_validations += 1;
                    downloaded_files += outcome.file_count;
                }
                Ok(None) => {}
                Err(error) => {
                    let display_id = validation
                        .request_number_trimmed()
                        .or_else(|| validation.verification_id_trimmed())
                        .unwrap_or_else(|| "validacion-sin-id".to_owned());
                    warnings.push(format!(
                        "No se pudo descargar la media de {display_id}: {error}"
                    ));
                }
            }
        }

        MediaBatchOutcome {
            downloaded_files,
            downloaded_validations,
            downloads_dir: self.downloads_dir.clone(),
            warnings,
        }
    }

    fn download_validation_media(
        &self,
        validation: &ValidationSnapshot,
    ) -> Result<Option<ValidationDownloadOutcome>> {
        let Some(verification_id) = validation.verification_id_trimmed() else {
            return Ok(None);
        };

        let index_path = self.index_dir.join(format!("{verification_id}.json"));
        if index_path.exists() {
            return Ok(None);
        }

        let Some(resource_url) = validation.resource_url_trimmed() else {
            return Ok(None);
        };

        let payload = self.fetch_resource_payload(&resource_url)?;
        let person_name = extract_person_name(&payload)
            .or_else(|| validation.applicant_name_trimmed())
            .unwrap_or_else(|| "persona-sin-nombre".to_owned());
        let target_dir = self.downloads_dir.join(build_validation_folder_name(
            &person_name,
            validation.request_number_trimmed().as_deref(),
            &verification_id,
        ));
        fs::create_dir_all(&target_dir).with_context(|| {
            format!("No se pudo crear la carpeta destino {:?}", target_dir)
        })?;

        let media_entries = extract_media_entries(&payload);
        let mut downloaded_files = Vec::new();

        for (index, entry) in media_entries.iter().enumerate() {
            let filename = build_download_filename(index, entry);
            let target_path = target_dir.join(filename);
            let body = self.download_media_file(&entry.url)?;
            fs::write(&target_path, body)
                .with_context(|| format!("No se pudo escribir {:?}", target_path))?;
            downloaded_files.push(target_path);
        }

        let index_payload = json!({
            "verification_id": verification_id,
            "request_number": validation.request_number_trimmed(),
            "person_name": person_name,
            "resource_url": resource_url,
            "downloaded_at": Local::now().to_rfc3339(),
            "file_count": downloaded_files.len(),
            "target_dir": target_dir.display().to_string(),
            "files": downloaded_files
                .iter()
                .map(|path| path.file_name().map(|value| value.to_string_lossy().to_string()).unwrap_or_default())
                .collect::<Vec<_>>(),
        });
        fs::write(&index_path, serde_json::to_vec_pretty(&index_payload)?)
            .with_context(|| format!("No se pudo escribir el indice {:?}", index_path))?;

        Ok(Some(ValidationDownloadOutcome {
            file_count: downloaded_files.len(),
        }))
    }

    fn fetch_resource_payload(&self, resource_url: &str) -> Result<Value> {
        let token = self.fetch_access_token()?;
        self.http
            .get(resource_url)
            .bearer_auth(token)
            .send()
            .context("No se pudo leer el recurso MetaMap.")?
            .error_for_status()
            .context("MetaMap devolvio error al leer el recurso de validacion.")?
            .json::<Value>()
            .context("No se pudo decodificar el recurso MetaMap.")
    }

    fn fetch_access_token(&self) -> Result<String> {
        let response = self
            .http
            .post("https://api.prod.metamap.com/oauth/")
            .basic_auth(&self.metamap_client_id, Some(&self.metamap_client_secret))
            .form(&[("grant_type", "client_credentials")])
            .send()
            .context("No se pudo solicitar el token OAuth de MetaMap.")?
            .error_for_status()
            .context("MetaMap devolvio error al solicitar el token OAuth.")?
            .json::<OAuthTokenResponse>()
            .context("No se pudo decodificar el token OAuth de MetaMap.")?;

        Ok(response.access_token)
    }

    fn download_media_file(&self, url: &str) -> Result<Vec<u8>> {
        let response = self
            .http
            .get(url)
            .send()
            .with_context(|| format!("No se pudo descargar {url}"))?
            .error_for_status()
            .with_context(|| format!("MetaMap devolvio error descargando {url}"))?;
        let bytes = response
            .bytes()
            .with_context(|| format!("No se pudo leer el contenido de {url}"))?;
        Ok(bytes.to_vec())
    }
}

fn extract_person_name(payload: &Value) -> Option<String> {
    first_filled([
        search_exact_string(
            payload,
            &["fullName", "full_name", "applicantName", "applicant_name"],
        ),
        combine_name_parts(
            search_exact_string(payload, &["firstName", "first_name"]),
            search_exact_string(payload, &["surname", "lastName", "last_name"]),
        ),
    ])
}

fn extract_media_entries(payload: &Value) -> Vec<MediaEntry> {
    let mut entries = Vec::new();
    let mut seen = HashSet::new();
    let mut path = Vec::new();
    visit_media_entries(payload, &mut path, &mut seen, &mut entries);
    entries
}

fn visit_media_entries(
    value: &Value,
    path: &mut Vec<String>,
    seen: &mut HashSet<String>,
    entries: &mut Vec<MediaEntry>,
) {
    match value {
        Value::Object(map) => {
            for (key, child) in map {
                path.push(key.clone());
                visit_media_entries(child, path, seen, entries);
                path.pop();
            }
        }
        Value::Array(items) => {
            for (index, child) in items.iter().enumerate() {
                path.push(index.to_string());
                visit_media_entries(child, path, seen, entries);
                path.pop();
            }
        }
        Value::String(url) => {
            let trimmed = url.trim();
            if trimmed.is_empty() || !trimmed.starts_with("https://") {
                return;
            }
            if !looks_like_media_url(path, trimmed) {
                return;
            }
            if !seen.insert(trimmed.to_owned()) {
                return;
            }
            entries.push(MediaEntry {
                path: path.clone(),
                url: trimmed.to_owned(),
            });
        }
        _ => {}
    }
}

fn looks_like_media_url(path: &[String], url: &str) -> bool {
    let normalized_path = path
        .iter()
        .map(|segment| segment.to_ascii_lowercase())
        .collect::<Vec<_>>()
        .join("/");

    if normalized_path.contains("selfie")
        || normalized_path.contains("photo")
        || normalized_path.contains("pdf")
        || normalized_path.contains("document")
        || normalized_path.contains("video")
        || normalized_path.contains("media")
        || normalized_path.contains("file")
    {
        return true;
    }

    Url::parse(url)
        .ok()
        .and_then(|parsed| parsed.host_str().map(|value| value.to_ascii_lowercase()))
        .is_some_and(|host| host.contains("media-cdn."))
}

fn search_exact_string(payload: &Value, keys: &[&str]) -> Option<String> {
    match payload {
        Value::Object(map) => {
            for key in keys {
                if let Some(value) = map.get(*key).and_then(value_to_string) {
                    return Some(value);
                }
            }
            map.values()
                .find_map(|value| search_exact_string(value, keys))
        }
        Value::Array(items) => items.iter().find_map(|value| search_exact_string(value, keys)),
        _ => None,
    }
}

fn value_to_string(value: &Value) -> Option<String> {
    match value {
        Value::Null => None,
        Value::String(text) => {
            let trimmed = text.trim();
            if trimmed.is_empty() {
                None
            } else {
                Some(trimmed.to_owned())
            }
        }
        Value::Number(number) => Some(number.to_string()),
        Value::Bool(value) => Some(value.to_string()),
        Value::Object(map) => map.get("value").and_then(value_to_string),
        _ => None,
    }
}

fn combine_name_parts(first: Option<String>, last: Option<String>) -> Option<String> {
    match (first, last) {
        (Some(first), Some(last)) => Some(format!("{first} {last}")),
        (Some(first), None) => Some(first),
        (None, Some(last)) => Some(last),
        (None, None) => None,
    }
}

fn first_filled(values: impl IntoIterator<Item = Option<String>>) -> Option<String> {
    values.into_iter().flatten().find(|value| !value.trim().is_empty())
}

fn build_validation_folder_name(
    person_name: &str,
    request_number: Option<&str>,
    verification_id: &str,
) -> String {
    let person_name = sanitize_component(person_name, "persona", 72);
    let request_part = request_number
        .map(|value| sanitize_component(value, "sin-solicitud", 24))
        .unwrap_or_else(|| "sin-solicitud".to_owned());
    let verification_id = sanitize_component(verification_id, "sin-id", 48);
    format!("{person_name}__{request_part}__{verification_id}")
}

fn build_download_filename(index: usize, entry: &MediaEntry) -> String {
    let path_label = sanitize_component(&entry.path.join("_"), "archivo", 72);
    let basename = extract_url_basename(&entry.url)
        .map(|value| sanitize_filename(&value, "archivo.bin"))
        .unwrap_or_else(|| format!("archivo_{:02}.bin", index + 1));
    format!("{:02}_{}_{}", index + 1, path_label, basename)
}

fn extract_url_basename(url: &str) -> Option<String> {
    let parsed = Url::parse(url).ok()?;
    let filename = parsed
        .path_segments()
        .and_then(|segments| segments.filter(|segment| !segment.is_empty()).next_back())?;
    let trimmed = filename.trim();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed.to_owned())
    }
}

fn sanitize_component(value: &str, fallback: &str, max_len: usize) -> String {
    let mut output = String::new();
    let mut previous_was_separator = false;

    for character in value.trim().chars() {
        if character.is_alphanumeric() {
            output.push(character);
            previous_was_separator = false;
            continue;
        }

        if !previous_was_separator {
            output.push('_');
            previous_was_separator = true;
        }
    }

    let sanitized = output.trim_matches('_');
    if sanitized.is_empty() {
        return fallback.to_owned();
    }

    sanitized.chars().take(max_len).collect()
}

fn sanitize_filename(value: &str, fallback: &str) -> String {
    let mut output = String::new();
    let mut previous_was_separator = false;

    for character in value.trim().chars() {
        if character.is_alphanumeric() || matches!(character, '.' | '-' | '_') {
            output.push(character);
            previous_was_separator = false;
            continue;
        }

        if !previous_was_separator {
            output.push('_');
            previous_was_separator = true;
        }
    }

    let sanitized = output.trim_matches('_');
    if sanitized.is_empty() {
        return fallback.to_owned();
    }

    sanitized.to_owned()
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{
        build_validation_folder_name, extract_media_entries, extract_person_name,
    };

    #[test]
    fn extracts_person_name_from_full_name_fields() {
        let payload = json!({
            "documents": [
                {
                    "fields": {
                        "fullName": {
                            "value": "MATIAS ADRIAN GOMEZ BANCHER"
                        }
                    }
                }
            ]
        });

        assert_eq!(
            extract_person_name(&payload).as_deref(),
            Some("MATIAS ADRIAN GOMEZ BANCHER")
        );
    }

    #[test]
    fn extracts_signed_pdfs_and_document_photos_but_not_regular_urls() {
        let payload = json!({
            "steps": [
                {
                    "data": {
                        "selfiePhotoUrl": "https://media-cdn.prod.metamap.com/selfies/production/selfie-1.jpeg?Expires=1"
                    }
                },
                {
                    "data": {
                        "touchSign": {
                            "mediaUrl": "http://media-server/media/media/internal.png"
                        },
                        "signedDocumentDetails": [
                            {
                                "pdfDocumentUrl": "https://media-cdn.prod.metamap.com/template-documents/production/doc-1.pdf?Expires=1"
                            }
                        ]
                    }
                }
            ],
            "documents": [
                {
                    "photos": [
                        "https://media-cdn.prod.metamap.com/documents/production/front.jpeg?Expires=1",
                        "https://media-cdn.prod.metamap.com/documents/production/back.jpeg?Expires=1"
                    ]
                }
            ],
            "deviceFingerprint": {
                "origin": "https://signup.metamap.com"
            }
        });

        let entries = extract_media_entries(&payload);
        let urls = entries
            .iter()
            .map(|entry| entry.url.as_str())
            .collect::<Vec<_>>();

        assert_eq!(urls.len(), 4);
        assert!(urls.iter().any(|url| url.contains("selfie-1.jpeg")));
        assert!(urls.iter().any(|url| url.contains("doc-1.pdf")));
        assert!(urls.iter().any(|url| url.contains("front.jpeg")));
        assert!(urls.iter().any(|url| url.contains("back.jpeg")));
        assert!(!urls.iter().any(|url| url.contains("signup.metamap.com")));
        assert!(!urls.iter().any(|url| url.contains("media-server")));
    }

    #[test]
    fn builds_folder_name_with_person_request_and_verification_id() {
        let folder = build_validation_folder_name(
            "Matias Adrian Gomez Bancher",
            Some("243471"),
            "69f0a7871319fc6eaa18a290",
        );

        assert_eq!(
            folder,
            "Matias_Adrian_Gomez_Bancher__243471__69f0a7871319fc6eaa18a290"
        );
    }
}
