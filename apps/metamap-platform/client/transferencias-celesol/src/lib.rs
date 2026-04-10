pub const APP_NAME: &str = "Transferencias Celesol";
pub const BUILD_TAG: &str = "1.01";
pub const APP_NAME_WITH_TAG: &str = "Transferencias Celesol 1.01";

pub mod app;
pub mod coinag_client;
pub mod completed_log;
pub mod config;
pub mod core_client;
pub mod logging;
pub mod models;
pub mod receipt;
pub mod secure_config;
pub mod server_client;
pub mod ssh_transport;
pub mod validation;
