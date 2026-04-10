use chrono::{DateTime, FixedOffset, Local};
use serde::Deserialize;

#[derive(Clone, Debug, Deserialize)]
pub struct ValidationSearchResponse {
    pub items: Vec<ValidationSnapshot>,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub struct ValidationSnapshot {
    #[serde(default)]
    pub verification_id: Option<String>,
    #[serde(default)]
    pub latest_event_name: Option<String>,
    #[serde(default)]
    pub normalized_status: Option<String>,
    #[serde(default)]
    pub resource_url: Option<String>,
    #[serde(default)]
    pub request_number: Option<String>,
    #[serde(default)]
    pub loan_number: Option<String>,
    #[serde(default)]
    pub amount_raw: Option<String>,
    #[serde(default)]
    pub amount_value: Option<String>,
    #[serde(default)]
    pub requested_amount_raw: Option<String>,
    #[serde(default)]
    pub requested_amount_value: Option<String>,
    #[serde(default)]
    pub applicant_name: Option<String>,
    #[serde(default)]
    pub document_number: Option<String>,
    #[serde(default)]
    pub first_received_at: Option<String>,
    #[serde(default)]
    pub last_received_at: Option<String>,
    #[serde(default)]
    pub latest_event_timestamp: Option<String>,
    #[serde(default)]
    pub completed_at: Option<String>,
    #[serde(default)]
    pub event_count: u64,
}

#[derive(Clone, Debug, Default)]
pub struct CoreSnapshot {
    pub request_number: String,
    pub status: Option<String>,
    pub amount: Option<String>,
    pub name: Option<String>,
    pub line: Option<String>,
    pub cuil: Option<String>,
    pub document_number: Option<String>,
}

#[derive(Clone, Debug)]
pub struct MonitorItem {
    pub id: String,
    pub verification_id: Option<String>,
    pub name: String,
    pub line: String,
    pub request_number: String,
    pub cuil: String,
    pub amount: String,
    pub event_at: Option<DateTime<Local>>,
    pub event_label: String,
    pub core_enriched: bool,
}

#[derive(Clone, Debug, Default)]
pub struct SnapshotSummary {
    pub total: usize,
    pub core_enriched: usize,
}

impl ValidationSnapshot {
    pub fn event_at(&self) -> Option<DateTime<FixedOffset>> {
        parse_timestamp(self.completed_at.as_deref())
            .or_else(|| parse_timestamp(self.last_received_at.as_deref()))
            .or_else(|| parse_timestamp(self.latest_event_timestamp.as_deref()))
            .or_else(|| parse_timestamp(self.first_received_at.as_deref()))
    }

    pub fn sort_at(&self) -> Option<DateTime<FixedOffset>> {
        parse_timestamp(self.last_received_at.as_deref()).or_else(|| self.event_at())
    }

    pub fn request_number_trimmed(&self) -> Option<String> {
        self.request_number
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_owned)
    }

    pub fn document_number_trimmed(&self) -> Option<String> {
        self.document_number
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_owned)
    }

    pub fn display_id(&self) -> String {
        if let Some(verification_id) = self
            .verification_id
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
        {
            return verification_id.to_owned();
        }

        if let Some(request_number) = self.request_number_trimmed() {
            return format!("request-{request_number}");
        }

        "validation-without-id".to_owned()
    }

    pub fn fallback_amount(&self) -> Option<String> {
        first_filled(
            [
                self.requested_amount_raw.as_deref(),
                self.amount_raw.as_deref(),
                self.requested_amount_value.as_deref(),
                self.amount_value.as_deref(),
            ]
            .into_iter()
            .flatten(),
        )
    }
}

pub fn normalize_digits(value: &str) -> String {
    value.chars().filter(|character| character.is_ascii_digit()).collect()
}

pub fn format_cuil(value: &str) -> String {
    let digits = normalize_digits(value);

    if digits.len() != 11 {
        return digits;
    }

    format!(
        "{}-{}-{}",
        &digits[0..2],
        &digits[2..10],
        &digits[10..11]
    )
}

pub fn parse_timestamp(value: Option<&str>) -> Option<DateTime<FixedOffset>> {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .and_then(|value| DateTime::parse_from_rfc3339(value).ok())
}

pub fn first_filled<'a>(values: impl IntoIterator<Item = &'a str>) -> Option<String> {
    values
        .into_iter()
        .map(str::trim)
        .find(|value| !value.is_empty())
        .map(str::to_owned)
}
