//! Python ai/crypto.py compatible RWENC1 snapshots.
//! Format: RWENC1 newline + JSON, scrypt(32768,8,1), AES-256-GCM with project-bound AAD.
use aes_gcm::{
    aead::{Aead, KeyInit, Payload},
    Aes256Gcm, Nonce,
};
use base64::{engine::general_purpose::STANDARD, Engine};
use rand::{rngs::OsRng, RngCore};
use scrypt::{scrypt, Params};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;
use zeroize::Zeroizing;

const MAGIC: &[u8] = b"RWENC1\n";
const MAX_PLAINTEXT: usize = 16_000_000;
const MAX_ENVELOPE: usize = 24_000_000;
const KDF_N: u32 = 32768;
const KDF_R: u32 = 8;
const KDF_P: u32 = 1;
const AAD_PREFIX: &[u8] = b"researchweave:encrypted-backup:v1:";
const PROJECT_MAGIC: &[u8] = b"RWPENC1\n";
const PROJECT_FORMAT: &str = "researchweave-rwproj-encrypted";
const PROJECT_MAX_PLAINTEXT: usize = 256 * 1024 * 1024;
const PROJECT_MAX_HEADER: usize = 16 * 1024;

#[derive(Debug, Error, PartialEq, Eq)]
pub enum CryptoError {
    #[error("invalid project, password, or content size")]
    InvalidInput,
    #[error("unsupported or malformed RWENC1 envelope")]
    UnsupportedFormat,
    #[error("authentication failed: incorrect password, project, or corrupted ciphertext")]
    AuthenticationFailed,
    #[error("cryptographic provider error")]
    CryptoFailure,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Receipt {
    pub format_version: u8,
    pub plaintext_sha256: String,
    pub encrypted_sha256: String,
    pub encrypted_size_bytes: usize,
    pub kdf: String,
    pub cipher: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectArchiveMetadata {
    pub project_id: String,
    pub project_revision: i64,
    pub plaintext_sha256: String,
    pub plaintext_bytes: usize,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProjectArchiveHeader {
    format: String,
    version: u8,
    cipher: String,
    kdf: String,
    scrypt_n: u32,
    scrypt_r: u32,
    scrypt_p: u32,
    salt: String,
    nonce: String,
    project_id: String,
    project_revision: i64,
    plaintext_sha256: String,
    plaintext_bytes: usize,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Envelope {
    version: u8,
    cipher: String,
    kdf: String,
    kdf_n: u32,
    kdf_r: u32,
    kdf_p: u32,
    salt: String,
    nonce: String,
    ciphertext: String,
}

fn aad(project_id: &str) -> Result<Vec<u8>, CryptoError> {
    if project_id.is_empty() || project_id.len() > 256 {
        return Err(CryptoError::InvalidInput);
    }
    let mut result = AAD_PREFIX.to_vec();
    result.extend_from_slice(project_id.as_bytes());
    Ok(result)
}

fn key(password: &str, salt: &[u8; 16]) -> Result<Zeroizing<[u8; 32]>, CryptoError> {
    if password.chars().count() < 12 || password.len() > 2048 {
        return Err(CryptoError::InvalidInput);
    }
    let params = Params::new(15, KDF_R, KDF_P, 32).map_err(|_| CryptoError::CryptoFailure)?;
    let mut derived = Zeroizing::new([0u8; 32]);
    scrypt(password.as_bytes(), salt, &params, &mut *derived)
        .map_err(|_| CryptoError::CryptoFailure)?;
    Ok(derived)
}

fn project_key(password: &str, salt: &[u8; 16]) -> Result<Zeroizing<[u8; 32]>, CryptoError> {
    if password.is_empty() || password.len() > 1024 {
        return Err(CryptoError::InvalidInput);
    }
    let params = Params::new(15, KDF_R, KDF_P, 32).map_err(|_| CryptoError::CryptoFailure)?;
    let mut derived = Zeroizing::new([0u8; 32]);
    scrypt(password.as_bytes(), salt, &params, &mut *derived)
        .map_err(|_| CryptoError::CryptoFailure)?;
    Ok(derived)
}

fn hex_sha256(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

/// Random 128-bit salt and 96-bit nonce are generated per encryption.
pub fn encrypt_backup(
    project_id: &str,
    plaintext: &[u8],
    password: &str,
) -> Result<(Vec<u8>, Receipt), CryptoError> {
    let associated = aad(project_id)?;
    if plaintext.is_empty() || plaintext.len() > MAX_PLAINTEXT {
        return Err(CryptoError::InvalidInput);
    }
    let mut salt = [0u8; 16];
    let mut nonce = [0u8; 12];
    OsRng.fill_bytes(&mut salt);
    OsRng.fill_bytes(&mut nonce);
    let secret = key(password, &salt)?;
    let cipher = Aes256Gcm::new_from_slice(&*secret).map_err(|_| CryptoError::CryptoFailure)?;
    let ciphertext = cipher
        .encrypt(
            Nonce::from_slice(&nonce),
            Payload {
                msg: plaintext,
                aad: &associated,
            },
        )
        .map_err(|_| CryptoError::CryptoFailure)?;
    let envelope = Envelope {
        version: 1,
        cipher: "AES-256-GCM".into(),
        kdf: "scrypt".into(),
        kdf_n: KDF_N,
        kdf_r: KDF_R,
        kdf_p: KDF_P,
        salt: STANDARD.encode(salt),
        nonce: STANDARD.encode(nonce),
        ciphertext: STANDARD.encode(ciphertext),
    };
    let mut output = MAGIC.to_vec();
    // serde_json::to_vec is valid for Python's RWENC1 reader, which checks fields, not ordering.
    output.extend(serde_json::to_vec(&envelope).map_err(|_| CryptoError::CryptoFailure)?);
    if output.len() > MAX_ENVELOPE {
        return Err(CryptoError::InvalidInput);
    }
    let receipt = Receipt {
        format_version: 1,
        plaintext_sha256: hex_sha256(plaintext),
        encrypted_sha256: hex_sha256(&output),
        encrypted_size_bytes: output.len(),
        kdf: "scrypt".into(),
        cipher: "AES-256-GCM".into(),
    };
    Ok((output, receipt))
}

pub fn decrypt_backup(
    project_id: &str,
    encrypted: &[u8],
    password: &str,
) -> Result<Vec<u8>, CryptoError> {
    let associated = aad(project_id)?;
    if encrypted.len() > MAX_ENVELOPE || !encrypted.starts_with(MAGIC) {
        return Err(CryptoError::UnsupportedFormat);
    }
    let envelope: Envelope = serde_json::from_slice(&encrypted[MAGIC.len()..])
        .map_err(|_| CryptoError::UnsupportedFormat)?;
    if envelope.version != 1
        || envelope.cipher != "AES-256-GCM"
        || envelope.kdf != "scrypt"
        || envelope.kdf_n != KDF_N
        || envelope.kdf_r != KDF_R
        || envelope.kdf_p != KDF_P
    {
        return Err(CryptoError::UnsupportedFormat);
    }
    let salt: [u8; 16] = STANDARD
        .decode(envelope.salt)
        .map_err(|_| CryptoError::UnsupportedFormat)?
        .try_into()
        .map_err(|_| CryptoError::UnsupportedFormat)?;
    let nonce: [u8; 12] = STANDARD
        .decode(envelope.nonce)
        .map_err(|_| CryptoError::UnsupportedFormat)?
        .try_into()
        .map_err(|_| CryptoError::UnsupportedFormat)?;
    // A base64 input bound prevents allocation of oversized decoded content.
    if envelope.ciphertext.len() > (MAX_PLAINTEXT + 16).div_ceil(3) * 4 + 4 {
        return Err(CryptoError::UnsupportedFormat);
    }
    let ciphertext = STANDARD
        .decode(envelope.ciphertext)
        .map_err(|_| CryptoError::UnsupportedFormat)?;
    if ciphertext.len() < 16 || ciphertext.len() > MAX_PLAINTEXT + 16 {
        return Err(CryptoError::UnsupportedFormat);
    }
    let secret = key(password, &salt)?;
    let cipher = Aes256Gcm::new_from_slice(&*secret).map_err(|_| CryptoError::CryptoFailure)?;
    cipher
        .decrypt(
            Nonce::from_slice(&nonce),
            Payload {
                msg: &ciphertext,
                aad: &associated,
            },
        )
        .map_err(|_| CryptoError::AuthenticationFailed)
}

/// Python evidence/encrypted_archive.py compatible RWPENC1 project archive.
///
/// The authenticated header is stored verbatim and used as AES-GCM AAD, so
/// readers do not depend on JSON object key ordering.
pub fn encrypt_project_archive_bytes(
    project_id: &str,
    project_revision: i64,
    plaintext: &[u8],
    password: &str,
) -> Result<Vec<u8>, CryptoError> {
    if project_id.is_empty()
        || project_id.len() > 256
        || project_revision < 0
        || plaintext.is_empty()
        || plaintext.len() > PROJECT_MAX_PLAINTEXT
    {
        return Err(CryptoError::InvalidInput);
    }
    let mut salt = [0u8; 16];
    let mut nonce = [0u8; 12];
    OsRng.fill_bytes(&mut salt);
    OsRng.fill_bytes(&mut nonce);
    let header = ProjectArchiveHeader {
        format: PROJECT_FORMAT.into(),
        version: 1,
        cipher: "AES-256-GCM".into(),
        kdf: "scrypt".into(),
        scrypt_n: KDF_N,
        scrypt_r: KDF_R,
        scrypt_p: KDF_P,
        salt: STANDARD.encode(salt),
        nonce: STANDARD.encode(nonce),
        project_id: project_id.to_owned(),
        project_revision,
        plaintext_sha256: hex_sha256(plaintext),
        plaintext_bytes: plaintext.len(),
    };
    let header_bytes = serde_json::to_vec(&header).map_err(|_| CryptoError::CryptoFailure)?;
    if header_bytes.is_empty() || header_bytes.len() > PROJECT_MAX_HEADER {
        return Err(CryptoError::CryptoFailure);
    }
    let secret = project_key(password, &salt)?;
    let cipher = Aes256Gcm::new_from_slice(&*secret).map_err(|_| CryptoError::CryptoFailure)?;
    let ciphertext = cipher
        .encrypt(
            Nonce::from_slice(&nonce),
            Payload {
                msg: plaintext,
                aad: &header_bytes,
            },
        )
        .map_err(|_| CryptoError::CryptoFailure)?;
    let mut output =
        Vec::with_capacity(PROJECT_MAGIC.len() + 4 + header_bytes.len() + ciphertext.len());
    output.extend_from_slice(PROJECT_MAGIC);
    output.extend_from_slice(&(header_bytes.len() as u32).to_be_bytes());
    output.extend_from_slice(&header_bytes);
    output.extend_from_slice(&ciphertext);
    if output.len() > PROJECT_MAX_PLAINTEXT + PROJECT_MAX_HEADER + 1024 {
        return Err(CryptoError::InvalidInput);
    }
    Ok(output)
}

pub fn decrypt_project_archive_bytes(
    encrypted: &[u8],
    password: &str,
) -> Result<(Vec<u8>, ProjectArchiveMetadata), CryptoError> {
    if encrypted.len() > PROJECT_MAX_PLAINTEXT + PROJECT_MAX_HEADER + 1024
        || encrypted.len() < PROJECT_MAGIC.len() + 4 + 16
        || !encrypted.starts_with(PROJECT_MAGIC)
    {
        return Err(CryptoError::UnsupportedFormat);
    }
    let length_offset = PROJECT_MAGIC.len();
    let header_len = u32::from_be_bytes(
        encrypted[length_offset..length_offset + 4]
            .try_into()
            .map_err(|_| CryptoError::UnsupportedFormat)?,
    ) as usize;
    if !(1..=PROJECT_MAX_HEADER).contains(&header_len) {
        return Err(CryptoError::UnsupportedFormat);
    }
    let header_start = length_offset + 4;
    let header_end = header_start
        .checked_add(header_len)
        .ok_or(CryptoError::UnsupportedFormat)?;
    if header_end >= encrypted.len() {
        return Err(CryptoError::UnsupportedFormat);
    }
    let header_bytes = &encrypted[header_start..header_end];
    let header: ProjectArchiveHeader =
        serde_json::from_slice(header_bytes).map_err(|_| CryptoError::UnsupportedFormat)?;
    if header.format != PROJECT_FORMAT
        || header.version != 1
        || header.cipher != "AES-256-GCM"
        || header.kdf != "scrypt"
        || header.scrypt_n != KDF_N
        || header.scrypt_r != KDF_R
        || header.scrypt_p != KDF_P
        || header.project_id.is_empty()
        || header.project_id.len() > 256
        || header.project_revision < 0
        || header.plaintext_bytes == 0
        || header.plaintext_bytes > PROJECT_MAX_PLAINTEXT
        || header.plaintext_sha256.len() != 64
        || !header
            .plaintext_sha256
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
    {
        return Err(CryptoError::UnsupportedFormat);
    }
    let salt: [u8; 16] = STANDARD
        .decode(header.salt)
        .map_err(|_| CryptoError::UnsupportedFormat)?
        .try_into()
        .map_err(|_| CryptoError::UnsupportedFormat)?;
    let nonce: [u8; 12] = STANDARD
        .decode(header.nonce)
        .map_err(|_| CryptoError::UnsupportedFormat)?
        .try_into()
        .map_err(|_| CryptoError::UnsupportedFormat)?;
    let ciphertext = &encrypted[header_end..];
    if ciphertext.len() < 16 || ciphertext.len() > PROJECT_MAX_PLAINTEXT + 16 {
        return Err(CryptoError::UnsupportedFormat);
    }
    let secret = project_key(password, &salt)?;
    let cipher = Aes256Gcm::new_from_slice(&*secret).map_err(|_| CryptoError::CryptoFailure)?;
    let plaintext = cipher
        .decrypt(
            Nonce::from_slice(&nonce),
            Payload {
                msg: ciphertext,
                aad: header_bytes,
            },
        )
        .map_err(|_| CryptoError::AuthenticationFailed)?;
    if plaintext.len() != header.plaintext_bytes
        || hex_sha256(&plaintext) != header.plaintext_sha256
    {
        return Err(CryptoError::AuthenticationFailed);
    }
    let metadata = ProjectArchiveMetadata {
        project_id: header.project_id,
        project_revision: header.project_revision,
        plaintext_sha256: header.plaintext_sha256,
        plaintext_bytes: header.plaintext_bytes,
    };
    Ok((plaintext, metadata))
}

#[cfg(test)]
mod tests {
    use super::*;
    const PASSWORD: &str = "correct long passphrase";
    #[test]
    fn roundtrip_and_nonce_randomness() {
        let (a, ra) = encrypt_backup("project-α", b"private dataset", PASSWORD).unwrap();
        let (b, rb) = encrypt_backup("project-α", b"private dataset", PASSWORD).unwrap();
        assert_ne!(a, b);
        assert_ne!(ra.encrypted_sha256, rb.encrypted_sha256);
        assert_eq!(
            decrypt_backup("project-α", &a, PASSWORD).unwrap(),
            b"private dataset"
        );
        assert_eq!(
            decrypt_backup("project-α", &b, PASSWORD).unwrap(),
            b"private dataset"
        );
    }
    #[test]
    fn wrong_password_scope_and_tamper_fail() {
        let (sealed, _) = encrypt_backup("project-a", b"secret", PASSWORD).unwrap();
        assert_eq!(
            decrypt_backup("project-a", &sealed, "incorrect passphrase"),
            Err(CryptoError::AuthenticationFailed)
        );
        assert_eq!(
            decrypt_backup("project-b", &sealed, PASSWORD),
            Err(CryptoError::AuthenticationFailed)
        );
        let mut envelope: serde_json::Value =
            serde_json::from_slice(&sealed[MAGIC.len()..]).unwrap();
        let encoded = envelope["ciphertext"].as_str().unwrap();
        let mut payload = STANDARD.decode(encoded).unwrap();
        payload[0] ^= 1;
        envelope["ciphertext"] = serde_json::Value::String(STANDARD.encode(payload));
        let mut tampered = MAGIC.to_vec();
        tampered.extend(serde_json::to_vec(&envelope).unwrap());
        assert_eq!(
            decrypt_backup("project-a", &tampered, PASSWORD),
            Err(CryptoError::AuthenticationFailed)
        );
    }
    #[test]
    fn rejects_unsupported_fields() {
        let (sealed, _) = encrypt_backup("project-a", b"secret", PASSWORD).unwrap();
        let mut envelope: serde_json::Value =
            serde_json::from_slice(&sealed[MAGIC.len()..]).unwrap();
        envelope["surprise"] = serde_json::Value::Bool(true);
        let mut invalid = MAGIC.to_vec();
        invalid.extend(serde_json::to_vec(&envelope).unwrap());
        assert_eq!(
            decrypt_backup("project-a", &invalid, PASSWORD),
            Err(CryptoError::UnsupportedFormat)
        );
    }

    #[test]
    fn decrypts_python_v012_fixture() {
        let fixture = include_bytes!("../tests/fixtures/python-v012.rwenc");
        let plaintext =
            decrypt_backup("interop-project", fixture, "compatibility password").unwrap();
        assert_eq!(
            plaintext,
            "Python 0.1.2 → Rust\nPersian: پژوهش\n".as_bytes()
        );
    }

    #[test]
    fn project_archive_envelope_roundtrips_and_authenticates_header() {
        let plaintext = b"PK\x03\x04portable project bytes \xf0\x9f\x8c\x8d";
        let sealed = encrypt_project_archive_bytes(
            "project-123",
            7,
            plaintext,
            "archive compatibility password",
        )
        .unwrap();
        assert!(sealed.starts_with(PROJECT_MAGIC));
        let (opened, metadata) =
            decrypt_project_archive_bytes(&sealed, "archive compatibility password").unwrap();
        assert_eq!(opened, plaintext);
        assert_eq!(metadata.project_id, "project-123");
        assert_eq!(metadata.project_revision, 7);
        assert_eq!(metadata.plaintext_bytes, plaintext.len());
        assert_eq!(metadata.plaintext_sha256, hex_sha256(plaintext));

        let mut tampered = sealed.clone();
        let header_len = u32::from_be_bytes(
            tampered[PROJECT_MAGIC.len()..PROJECT_MAGIC.len() + 4]
                .try_into()
                .unwrap(),
        ) as usize;
        let header_start = PROJECT_MAGIC.len() + 4;
        let header_end = header_start + header_len;
        let mut header: serde_json::Value =
            serde_json::from_slice(&tampered[header_start..header_end]).unwrap();
        header["project_revision"] = serde_json::json!(8);
        let replacement = serde_json::to_vec(&header).unwrap();
        assert_eq!(replacement.len(), header_len);
        tampered[header_start..header_end].copy_from_slice(&replacement);
        assert_eq!(
            decrypt_project_archive_bytes(&tampered, "archive compatibility password"),
            Err(CryptoError::AuthenticationFailed)
        );
    }

    #[test]
    fn project_archive_envelope_rejects_wrong_password_and_oversized_metadata() {
        let sealed =
            encrypt_project_archive_bytes("p", 0, b"archive", "valid archive password").unwrap();
        assert_eq!(
            decrypt_project_archive_bytes(&sealed, "wrong password"),
            Err(CryptoError::AuthenticationFailed)
        );
        assert_eq!(
            encrypt_project_archive_bytes("", 0, b"archive", "valid archive password"),
            Err(CryptoError::InvalidInput)
        );
        assert_eq!(
            encrypt_project_archive_bytes("p", -1, b"archive", "valid archive password"),
            Err(CryptoError::InvalidInput)
        );
    }
}
