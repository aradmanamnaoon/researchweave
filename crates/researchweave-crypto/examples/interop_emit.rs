use researchweave_crypto::encrypt_backup;
use std::env;
use std::fs;
use std::process::ExitCode;

fn main() -> ExitCode {
    let Some(destination) = env::args_os().nth(1) else {
        eprintln!("usage: interop_emit <destination>");
        return ExitCode::from(2);
    };
    let plaintext = "Rust → Python 0.1.2\nPersian: پژوهش\n".as_bytes();
    let (sealed, receipt) =
        match encrypt_backup("interop-project", plaintext, "compatibility password") {
            Ok(value) => value,
            Err(error) => {
                eprintln!("encryption failed: {error}");
                return ExitCode::FAILURE;
            }
        };
    if let Err(error) = fs::write(destination, sealed) {
        eprintln!("write failed: {error}");
        return ExitCode::FAILURE;
    }
    println!("{}", receipt.plaintext_sha256);
    ExitCode::SUCCESS
}
