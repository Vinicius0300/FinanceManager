//! Onde ficam o executável do backend instalado e os dados do usuário.
//!
//! - Backend empacotado (PyInstaller `onedir`): o instalador copia a pasta
//!   `financas-backend\` para a pasta de recursos do app (`resource_dir()`, que no Windows é a
//!   própria pasta de instalação). Ver `tauri.instalador.conf.json` (`bundle.resources`).
//! - Dados do usuário: `%APPDATA%\Financas\` (ou `FINANCAS_DATA_DIR`), igual a
//!   `backend/app/core/paths.py`. Nunca a pasta de instalação.
//! - `logs\backend-stderr.log`: saída de erro do backend, sobrescrita a cada abertura. Pega o
//!   que acontece **antes** de o Python configurar o `backend.log` (import faltando no
//!   executável, erro de configuração com código 2 do `entrypoint.py`).

use std::ffi::OsString;
use std::fs::{self, File};
use std::io;
use std::path::{Path, PathBuf};

/// Subpasta do backend dentro dos recursos do app.
pub const PASTA_BACKEND: &str = "financas-backend";
/// Executável do backend dentro de `PASTA_BACKEND`.
pub const EXE_BACKEND: &str = if cfg!(windows) {
    "financas-backend.exe"
} else {
    "financas-backend"
};
/// Nome da pasta de dados dentro de `%APPDATA%`.
pub const PASTA_DADOS: &str = "Financas";
/// Arquivo com o stderr do backend (pasta `logs` dos dados).
pub const ARQUIVO_STDERR: &str = "backend-stderr.log";

/// Caminho do executável do backend instalado, a partir da pasta de recursos do app.
pub fn executavel_backend(pasta_recursos: &Path) -> PathBuf {
    pasta_recursos.join(PASTA_BACKEND).join(EXE_BACKEND)
}

/// Pasta de dados do usuário: `FINANCAS_DATA_DIR` (se definido e não vazio) ou
/// `%APPDATA%\Financas`. `None` se nenhuma das duas variáveis existir.
pub fn pasta_dados_de(data_dir: Option<OsString>, appdata: Option<OsString>) -> Option<PathBuf> {
    match data_dir.filter(|valor| !valor.is_empty()) {
        Some(valor) => Some(PathBuf::from(valor)),
        None => appdata
            .filter(|valor| !valor.is_empty())
            .map(|valor| PathBuf::from(valor).join(PASTA_DADOS)),
    }
}

/// Pasta de logs do usuário lendo as variáveis de ambiente do processo.
pub fn pasta_logs() -> Option<PathBuf> {
    pasta_dados_de(
        std::env::var_os("FINANCAS_DATA_DIR"),
        std::env::var_os("APPDATA"),
    )
    .map(|dados| dados.join("logs"))
}

/// Cria a pasta de logs (se faltar) e abre o `backend-stderr.log` **vazio** (sobrescreve o da
/// abertura anterior).
pub fn abrir_log_stderr(pasta_logs: &Path) -> io::Result<(File, PathBuf)> {
    fs::create_dir_all(pasta_logs)?;
    let caminho = pasta_logs.join(ARQUIVO_STDERR);
    let arquivo = File::create(&caminho)?;
    Ok((arquivo, caminho))
}

#[cfg(test)]
mod testes {
    use super::*;
    use std::io::Write;
    use std::process::{Command, Stdio};
    use std::sync::atomic::{AtomicU32, Ordering};

    /// Pasta temporária única por teste (os testes rodam em paralelo).
    fn pasta_temporaria(nome: &str) -> PathBuf {
        static CONTADOR: AtomicU32 = AtomicU32::new(0);
        let n = CONTADOR.fetch_add(1, Ordering::SeqCst);
        let pasta =
            std::env::temp_dir().join(format!("financas-teste-{nome}-{}-{n}", std::process::id()));
        let _ = fs::remove_dir_all(&pasta);
        pasta
    }

    #[test]
    fn executavel_fica_na_pasta_do_backend_dentro_dos_recursos() {
        let recursos = PathBuf::from(r"C:\Users\x\AppData\Local\Financas");
        assert_eq!(
            executavel_backend(&recursos),
            recursos.join("financas-backend").join(EXE_BACKEND)
        );
        #[cfg(windows)]
        assert_eq!(
            executavel_backend(&recursos),
            PathBuf::from(
                r"C:\Users\x\AppData\Local\Financas\financas-backend\financas-backend.exe"
            )
        );
    }

    #[test]
    fn pasta_de_dados_usa_appdata_ou_a_variavel_de_teste() {
        let appdata = Some(OsString::from(r"C:\Users\x\AppData\Roaming"));
        assert_eq!(
            pasta_dados_de(None, appdata.clone()),
            Some(PathBuf::from(r"C:\Users\x\AppData\Roaming").join("Financas"))
        );
        // FINANCAS_DATA_DIR (testes) tem prioridade, como no backend Python.
        assert_eq!(
            pasta_dados_de(Some(OsString::from(r"D:\dados")), appdata.clone()),
            Some(PathBuf::from(r"D:\dados"))
        );
        // Variável vazia é ignorada.
        assert_eq!(
            pasta_dados_de(Some(OsString::new()), appdata),
            Some(PathBuf::from(r"C:\Users\x\AppData\Roaming").join("Financas"))
        );
        assert_eq!(pasta_dados_de(None, None), None);
    }

    #[test]
    fn log_de_stderr_cria_a_pasta_e_e_sobrescrito_a_cada_abertura() {
        let pasta = pasta_temporaria("stderr").join("logs");
        let (mut arquivo, caminho) = abrir_log_stderr(&pasta).expect("abrir o log");
        assert_eq!(caminho, pasta.join("backend-stderr.log"));
        arquivo.write_all(b"falha antiga").unwrap();
        drop(arquivo);

        let (_arquivo, caminho) = abrir_log_stderr(&pasta).expect("reabrir o log");
        assert_eq!(fs::read_to_string(&caminho).unwrap(), "");
        let _ = fs::remove_dir_all(pasta.parent().unwrap());
    }

    #[test]
    fn stderr_de_um_processo_vai_para_o_arquivo() {
        // Mesmo encaminhamento que o backend usa (Stdio a partir do arquivo aberto).
        let pasta = pasta_temporaria("processo").join("logs");
        let (arquivo, caminho) = abrir_log_stderr(&pasta).unwrap();
        let mut comando = if cfg!(windows) {
            let mut c = Command::new("cmd");
            c.args(["/C", "echo ModuleNotFoundError: No module named x 1>&2"]);
            c
        } else {
            let mut c = Command::new("sh");
            c.args(["-c", "echo 'ModuleNotFoundError: No module named x' 1>&2"]);
            c
        };
        let status = comando
            .stdout(Stdio::null())
            .stderr(Stdio::from(arquivo))
            .status()
            .unwrap();
        assert!(status.success());
        let conteudo = fs::read_to_string(&caminho).unwrap();
        assert!(
            conteudo.contains("ModuleNotFoundError: No module named x"),
            "{conteudo:?}"
        );
        let _ = fs::remove_dir_all(pasta.parent().unwrap());
    }
}
