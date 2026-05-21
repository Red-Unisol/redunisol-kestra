use std::{io, thread};

#[cfg(target_os = "windows")]
use std::{
    mem::size_of,
    ptr::{null, null_mut},
    time::Duration,
};

#[cfg(target_os = "windows")]
use windows_sys::Win32::{
    Foundation::{ERROR_CLASS_ALREADY_EXISTS, HWND, LPARAM, LRESULT, WPARAM},
    System::LibraryLoader::GetModuleHandleW,
    UI::{
        Shell::{
            NIF_ICON, NIF_INFO, NIF_MESSAGE, NIF_TIP, NIIF_INFO, NIM_ADD, NIM_DELETE, NIM_MODIFY,
            NOTIFYICONDATAW, Shell_NotifyIconW,
        },
        WindowsAndMessaging::{
            CreateWindowExW, DefWindowProcW, DestroyWindow, IDI_INFORMATION, LoadIconW,
            RegisterClassW, WM_USER, WNDCLASSW, WS_OVERLAPPED,
        },
    },
};

#[cfg(target_os = "windows")]
const BALLOON_TIMEOUT_MS: u32 = 5_000;

#[cfg(target_os = "windows")]
const NOTIFICATION_ICON_ID: u32 = 1;

#[cfg(target_os = "windows")]
const NOTIFICATION_CALLBACK_MESSAGE: u32 = WM_USER + 1;

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
fn notify_impl(title: &str, body: &str) -> io::Result<()> {
    unsafe { show_windows_notification(title, body) }
}

#[cfg(not(target_os = "windows"))]
fn notify_impl(title: &str, body: &str) -> io::Result<()> {
    log::info!("Nueva validacion: {title} | {body}");
    Ok(())
}

#[cfg(target_os = "windows")]
unsafe fn show_windows_notification(title: &str, body: &str) -> io::Result<()> {
    let hwnd = unsafe { create_notification_window()? };
    let mut icon_data = unsafe { base_icon_data(hwnd) };

    if unsafe { Shell_NotifyIconW(NIM_ADD, &icon_data) } == 0 {
        let error = io::Error::last_os_error();
        unsafe {
            DestroyWindow(hwnd);
        }
        return Err(error);
    }

    icon_data.uFlags = NIF_INFO;
    icon_data.dwInfoFlags = NIIF_INFO;
    icon_data.Anonymous.uTimeout = BALLOON_TIMEOUT_MS;
    copy_wide_truncated(title, &mut icon_data.szInfoTitle);
    copy_wide_truncated(body, &mut icon_data.szInfo);

    if unsafe { Shell_NotifyIconW(NIM_MODIFY, &icon_data) } == 0 {
        let error = io::Error::last_os_error();
        unsafe {
            Shell_NotifyIconW(NIM_DELETE, &icon_data);
            DestroyWindow(hwnd);
        }
        return Err(error);
    }

    thread::sleep(Duration::from_millis(u64::from(BALLOON_TIMEOUT_MS) + 500));

    unsafe {
        Shell_NotifyIconW(NIM_DELETE, &icon_data);
        DestroyWindow(hwnd);
    }

    Ok(())
}

#[cfg(target_os = "windows")]
unsafe fn create_notification_window() -> io::Result<HWND> {
    let class_name = wide_null("ValidacionMetamapNotificationWindow");
    let instance = unsafe { GetModuleHandleW(null()) };
    if instance.is_null() {
        return Err(io::Error::last_os_error());
    }

    let window_class = WNDCLASSW {
        lpfnWndProc: Some(notification_window_proc),
        hInstance: instance,
        lpszClassName: class_name.as_ptr(),
        ..Default::default()
    };

    if unsafe { RegisterClassW(&window_class) } == 0 {
        let error = io::Error::last_os_error();
        if error.raw_os_error() != Some(ERROR_CLASS_ALREADY_EXISTS as i32) {
            return Err(error);
        }
    }

    let hwnd = unsafe {
        CreateWindowExW(
            0,
            class_name.as_ptr(),
            class_name.as_ptr(),
            WS_OVERLAPPED,
            0,
            0,
            0,
            0,
            null_mut(),
            null_mut(),
            instance,
            null(),
        )
    };
    if hwnd.is_null() {
        return Err(io::Error::last_os_error());
    }

    Ok(hwnd)
}

#[cfg(target_os = "windows")]
unsafe fn base_icon_data(hwnd: HWND) -> NOTIFYICONDATAW {
    let mut icon_data = NOTIFYICONDATAW {
        cbSize: size_of::<NOTIFYICONDATAW>() as u32,
        hWnd: hwnd,
        uID: NOTIFICATION_ICON_ID,
        uFlags: NIF_MESSAGE | NIF_ICON | NIF_TIP,
        uCallbackMessage: NOTIFICATION_CALLBACK_MESSAGE,
        hIcon: unsafe { LoadIconW(null_mut(), IDI_INFORMATION) },
        ..Default::default()
    };
    copy_wide_truncated("Validacion MetaMap", &mut icon_data.szTip);
    icon_data
}

#[cfg(target_os = "windows")]
unsafe extern "system" fn notification_window_proc(
    hwnd: HWND,
    message: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    unsafe { DefWindowProcW(hwnd, message, wparam, lparam) }
}

#[cfg(target_os = "windows")]
fn copy_wide_truncated(value: &str, destination: &mut [u16]) {
    if destination.is_empty() {
        return;
    }

    destination.fill(0);
    let max_chars = destination.len() - 1;
    for (slot, code_unit) in destination
        .iter_mut()
        .take(max_chars)
        .zip(value.encode_utf16())
    {
        *slot = code_unit;
    }
}

#[cfg(target_os = "windows")]
fn wide_null(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(std::iter::once(0)).collect()
}
