use std::{process::Command, thread};

pub fn notify(title: &str, body: &str) {
    let title = title.to_owned();
    let body = body.to_owned();

    thread::spawn(move || {
        if let Err(error) = notify_impl(&title, &body) {
            log::warn!("No se pudo emitir la notificacion local: {error}");
        }
    });
}

#[cfg(target_os = "windows")]
fn notify_impl(title: &str, body: &str) -> std::io::Result<()> {
    let title = escape_for_powershell_single_quotes(title);
    let body = escape_for_powershell_single_quotes(body);
    let script = format!(
        concat!(
            "Add-Type -AssemblyName System.Windows.Forms; ",
            "Add-Type -AssemblyName System.Drawing; ",
            "$n = New-Object System.Windows.Forms.NotifyIcon; ",
            "$n.Icon = [System.Drawing.SystemIcons]::Information; ",
            "$n.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info; ",
            "$n.BalloonTipTitle = '{}'; ",
            "$n.BalloonTipText = '{}'; ",
            "$n.Visible = $true; ",
            "$n.ShowBalloonTip(5000); ",
            "Start-Sleep -Milliseconds 5500; ",
            "$n.Dispose();"
        ),
        title,
        body,
    );

    Command::new("powershell")
        .args([
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            &script,
        ])
        .spawn()?;

    Ok(())
}

#[cfg(not(target_os = "windows"))]
fn notify_impl(title: &str, body: &str) -> std::io::Result<()> {
    log::info!("Nueva validacion: {title} | {body}");
    Ok(())
}

#[cfg(target_os = "windows")]
fn escape_for_powershell_single_quotes(value: &str) -> String {
    value.replace('\'', "''")
}
