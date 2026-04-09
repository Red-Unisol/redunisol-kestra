use aes_gcm::{
    Aes256Gcm, Nonce,
    aead::{Aead, KeyInit},
};
use anyhow::{Context, Result, anyhow};
use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64_STANDARD};
use pbkdf2::pbkdf2_hmac;
use rand::{RngCore, rngs::OsRng};
use serde::{Deserialize, Serialize};
use sha2::Sha256;

const ENCRYPTED_CONFIG_VERSION: u32 = 1;
const ENCRYPTED_CONFIG_ITERATIONS: u32 = 600_000;
const SALT_LEN: usize = 16;
const NONCE_LEN: usize = 12;

#[derive(Debug, Serialize, Deserialize)]
struct EncryptedConfigEnvelope {
    version: u32,
    kdf: String,
    iterations: u32,
    salt: String,
    nonce: String,
    ciphertext: String,
}

pub fn encrypt_config_text(plaintext: &str, passphrase: &str) -> Result<String> {
    let passphrase = normalized_passphrase(passphrase)?;

    let mut salt = [0_u8; SALT_LEN];
    let mut nonce = [0_u8; NONCE_LEN];
    OsRng.fill_bytes(&mut salt);
    OsRng.fill_bytes(&mut nonce);

    let key = derive_key(passphrase, &salt, ENCRYPTED_CONFIG_ITERATIONS);
    let cipher = Aes256Gcm::new_from_slice(&key).context("No se pudo inicializar AES-256-GCM.")?;
    let ciphertext = cipher
        .encrypt(Nonce::from_slice(&nonce), plaintext.as_bytes())
        .map_err(|_| anyhow!("No se pudo cifrar la configuracion."))?;

    serde_json::to_string_pretty(&EncryptedConfigEnvelope {
        version: ENCRYPTED_CONFIG_VERSION,
        kdf: "pbkdf2-sha256".to_owned(),
        iterations: ENCRYPTED_CONFIG_ITERATIONS,
        salt: BASE64_STANDARD.encode(salt),
        nonce: BASE64_STANDARD.encode(nonce),
        ciphertext: BASE64_STANDARD.encode(ciphertext),
    })
    .context("No se pudo serializar el archivo de configuracion cifrado.")
}

pub fn decrypt_config_text(ciphertext: &str, passphrase: &str) -> Result<String> {
    let passphrase = normalized_passphrase(passphrase)?;
    let envelope = serde_json::from_str::<EncryptedConfigEnvelope>(ciphertext)
        .context("El archivo cifrado no tiene JSON valido.")?;

    if envelope.version != ENCRYPTED_CONFIG_VERSION {
        return Err(anyhow!(
            "Version de archivo cifrado no soportada: {}.",
            envelope.version
        ));
    }
    if envelope.kdf.trim() != "pbkdf2-sha256" {
        return Err(anyhow!(
            "KDF no soportado en archivo cifrado: {}.",
            envelope.kdf
        ));
    }

    let salt = BASE64_STANDARD
        .decode(envelope.salt.as_bytes())
        .context("Salt invalido en archivo cifrado.")?;
    if salt.len() != SALT_LEN {
        return Err(anyhow!("Salt invalido en archivo cifrado."));
    }

    let nonce = BASE64_STANDARD
        .decode(envelope.nonce.as_bytes())
        .context("Nonce invalido en archivo cifrado.")?;
    if nonce.len() != NONCE_LEN {
        return Err(anyhow!("Nonce invalido en archivo cifrado."));
    }

    let ciphertext = BASE64_STANDARD
        .decode(envelope.ciphertext.as_bytes())
        .context("Ciphertext invalido en archivo cifrado.")?;

    let key = derive_key(passphrase, &salt, envelope.iterations);
    let cipher = Aes256Gcm::new_from_slice(&key).context("No se pudo inicializar AES-256-GCM.")?;
    let plaintext = cipher
        .decrypt(Nonce::from_slice(&nonce), ciphertext.as_ref())
        .map_err(|_| anyhow!("Passphrase invalida o archivo cifrado corrupto."))?;

    String::from_utf8(plaintext).context("La configuracion desencriptada no es UTF-8 valida.")
}

fn normalized_passphrase(passphrase: &str) -> Result<&str> {
    let passphrase = passphrase.trim();
    if passphrase.is_empty() {
        return Err(anyhow!("La passphrase no puede estar vacia."));
    }
    Ok(passphrase)
}

fn derive_key(passphrase: &str, salt: &[u8], iterations: u32) -> [u8; 32] {
    let mut key = [0_u8; 32];
    pbkdf2_hmac::<Sha256>(passphrase.as_bytes(), salt, iterations, &mut key);
    key
}

#[cfg(test)]
mod tests {
    use super::{decrypt_config_text, encrypt_config_text};

    #[test]
    fn encrypted_config_roundtrip() {
        let encrypted = encrypt_config_text("FOO=bar\nBAZ=1\n", "secret-123").unwrap();
        let decrypted = decrypt_config_text(&encrypted, "secret-123").unwrap();
        assert_eq!(decrypted, "FOO=bar\nBAZ=1\n");
    }

    #[test]
    fn encrypted_config_rejects_wrong_passphrase() {
        let encrypted = encrypt_config_text("FOO=bar\n", "secret-123").unwrap();
        let error = decrypt_config_text(&encrypted, "otro-secret")
            .expect_err("expected decryption to fail");
        assert!(
            error
                .to_string()
                .contains("Passphrase invalida o archivo cifrado corrupto")
        );
    }
}
