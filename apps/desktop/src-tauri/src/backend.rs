//! Ciclo de vida do backend Python (sidecar).
//!
//! 1. Escolhe uma porta livre em 127.0.0.1 e gera um token aleatório de sessão.
//! 2. Inicia o backend passando porta, token e o PID do app por variáveis de ambiente
//!    (o token não vai na linha de comando para não aparecer na lista de processos).
//! 3. Associa o processo a um Job Object (Windows): se o app morrer, o backend morre junto.
//! 4. Aguarda o `GET /health` responder (com timeout) antes de liberar a UI.
//! 5. Ao fechar: pede encerramento gracioso e, se não sair a tempo, força (kill).

use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::State;

#[cfg(windows)]
use crate::job::JobObject;

const TIMEOUT_INICIO: Duration = Duration::from_secs(30);
const TIMEOUT_ENCERRAMENTO: Duration = Duration::from_secs(3);
const FOLGA_APOS_PARAR: Duration = Duration::from_millis(300);
const INTERVALO_VERIFICACAO: Duration = Duration::from_millis(150);
const TIMEOUT_HTTP: Duration = Duration::from_millis(800);
const DICA_LOGS: &str = "Veja os detalhes em %APPDATA%\\Financas\\logs\\backend.log.";

/// Dados que o React recebe via `invoke("conexao_backend")`.
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ConexaoBackend {
    url_base: String,
    token: String,
}

#[derive(Clone)]
enum Estado {
    Iniciando,
    Pronto(ConexaoBackend),
    Falhou(String),
}

struct Processo {
    filho: Child,
    porta: u16,
    token: String,
    #[cfg(windows)]
    _job: Option<JobObject>,
}

struct Interno {
    estado: Mutex<Estado>,
    processo: Mutex<Option<Processo>>,
    /// Incrementada a cada início/encerramento; invalida inicializações antigas.
    geracao: AtomicU64,
}

#[derive(Clone)]
pub struct GerenciadorBackend(Arc<Interno>);

impl Default for GerenciadorBackend {
    fn default() -> Self {
        Self(Arc::new(Interno {
            estado: Mutex::new(Estado::Iniciando),
            processo: Mutex::new(None),
            geracao: AtomicU64::new(0),
        }))
    }
}

/// Um mutex "envenenado" (panic em outra thread) não deve derrubar o app.
fn travar<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(|erro| erro.into_inner())
}

impl GerenciadorBackend {
    /// Inicia o backend em segundo plano; o resultado fica disponível em `estado`.
    pub fn iniciar(&self) {
        let geracao = self.0.geracao.fetch_add(1, Ordering::SeqCst) + 1;
        *travar(&self.0.estado) = Estado::Iniciando;

        let interno = Arc::clone(&self.0);
        let disparo = thread::Builder::new()
            .name("backend-inicio".into())
            .spawn(move || {
                let resultado = iniciar_e_aguardar(&interno, geracao);
                if interno.geracao.load(Ordering::SeqCst) != geracao {
                    return; // houve reinício/encerramento no meio do caminho
                }
                *travar(&interno.estado) = match resultado {
                    Ok(conexao) => Estado::Pronto(conexao),
                    Err(mensagem) => {
                        eprintln!("[financas] falha ao iniciar o backend: {mensagem}");
                        Estado::Falhou(mensagem)
                    }
                };
            });
        if let Err(erro) = disparo {
            *travar(&self.0.estado) =
                Estado::Falhou(format!("Não foi possível iniciar o serviço interno: {erro}"));
        }
    }

    /// Encerra o backend (gracioso e, se preciso, forçado). Bloqueia até ~3 s.
    pub fn encerrar(&self) {
        self.0.geracao.fetch_add(1, Ordering::SeqCst);
        let processo = travar(&self.0.processo).take();
        if let Some(processo) = processo {
            encerrar_processo(processo);
        }
    }

    fn estado(&self) -> Estado {
        travar(&self.0.estado).clone()
    }
}

fn iniciar_e_aguardar(interno: &Interno, geracao: u64) -> Result<ConexaoBackend, String> {
    let porta =
        porta_livre().map_err(|e| format!("Não foi possível reservar uma porta local: {e}"))?;
    let token = gerar_token()?;
    let processo = iniciar_processo(porta, &token)?;

    {
        let mut guarda = travar(&interno.processo);
        if interno.geracao.load(Ordering::SeqCst) != geracao {
            drop(guarda);
            encerrar_processo(processo);
            return Err("Inicialização cancelada.".into());
        }
        let anterior = guarda.replace(processo);
        drop(guarda);
        if let Some(anterior) = anterior {
            encerrar_processo(anterior);
        }
    }

    let limite = Instant::now() + TIMEOUT_INICIO;
    loop {
        if interno.geracao.load(Ordering::SeqCst) != geracao {
            return Err("Inicialização cancelada.".into());
        }
        {
            let mut guarda = travar(&interno.processo);
            let Some(atual) = guarda.as_mut() else {
                return Err("O serviço interno foi encerrado durante a inicialização.".into());
            };
            if let Ok(Some(status)) = atual.filho.try_wait() {
                *guarda = None;
                return Err(format!(
                    "O serviço interno fechou logo após iniciar ({}). {DICA_LOGS}",
                    descrever_saida(status)
                ));
            }
        }

        if requisicao_http(porta, "GET", "/health", None) == Some(200) {
            return Ok(ConexaoBackend {
                url_base: format!("http://127.0.0.1:{porta}"),
                token,
            });
        }

        if Instant::now() >= limite {
            let processo = travar(&interno.processo).take();
            if let Some(processo) = processo {
                encerrar_processo(processo);
            }
            return Err(format!(
                "O serviço interno não respondeu em {} segundos. {DICA_LOGS}",
                TIMEOUT_INICIO.as_secs()
            ));
        }
        thread::sleep(INTERVALO_VERIFICACAO);
    }
}

/// Comando do backend. Em desenvolvimento usa o Python do venv com reload;
/// no app instalado, o executável empacotado ao lado do app.
fn comando_backend() -> Result<Command, String> {
    if cfg!(debug_assertions) {
        let pasta = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../backend");
        let python = if cfg!(windows) {
            pasta.join(".venv").join("Scripts").join("python.exe")
        } else {
            pasta.join(".venv").join("bin").join("python")
        };
        if !python.exists() {
            return Err(format!(
                "Ambiente Python do backend não encontrado em {}. \
                 Rode scripts\\2_preparar_projeto.bat e tente novamente.",
                python.display()
            ));
        }
        let mut comando = Command::new(python);
        comando.arg("entrypoint.py").arg("--reload").current_dir(pasta);
        Ok(comando)
    } else {
        let exe = std::env::current_exe()
            .map_err(|e| format!("Não foi possível localizar o aplicativo: {e}"))?;
        let pasta = exe.parent().map(PathBuf::from).unwrap_or_default();
        let sidecar = pasta.join(if cfg!(windows) {
            "financas-backend.exe"
        } else {
            "financas-backend"
        });
        if !sidecar.exists() {
            return Err(format!(
                "Executável do serviço interno não encontrado ({}). Reinstale o aplicativo.",
                sidecar.display()
            ));
        }
        Ok(Command::new(sidecar))
    }
}

fn iniciar_processo(porta: u16, token: &str) -> Result<Processo, String> {
    let mut comando = comando_backend()?;
    comando
        .env("FINANCAS_PORTA", porta.to_string())
        .env("FINANCAS_TOKEN", token)
        .env("FINANCAS_PID_PAI", std::process::id().to_string())
        .stdin(Stdio::null());

    if cfg!(debug_assertions) {
        // Logs do backend aparecem no terminal do `tauri dev`.
        comando.env("FINANCAS_DEV", "1");
    } else {
        comando.stdout(Stdio::null()).stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            comando.creation_flags(CREATE_NO_WINDOW);
        }
    }

    let filho = comando
        .spawn()
        .map_err(|e| format!("Não foi possível iniciar o serviço interno: {e}"))?;

    #[cfg(windows)]
    let job = match JobObject::criar().and_then(|job| job.associar(&filho).map(|()| job)) {
        Ok(job) => Some(job),
        Err(erro) => {
            // Sem o job, o watchdog do Python ainda encerra o backend se o app morrer.
            eprintln!("[financas] não foi possível criar o Job Object: {erro}");
            None
        }
    };

    Ok(Processo {
        filho,
        porta,
        token: token.to_owned(),
        #[cfg(windows)]
        _job: job,
    })
}

fn encerrar_processo(mut processo: Processo) {
    // 1) Pedido gracioso pela API (o backend responde 202 e encerra em seguida).
    let _ = requisicao_http(
        processo.porta,
        "POST",
        "/api/sistema/encerrar",
        Some(&processo.token),
    );

    // 2) Espera o processo sair. Em desenvolvimento o supervisor do reload do uvicorn
    //    não sai sozinho (e mantém a porta aberta); basta o worker parar de responder.
    let limite = Instant::now() + TIMEOUT_ENCERRAMENTO;
    let mut parou_em: Option<Instant> = None;
    while Instant::now() < limite {
        if matches!(processo.filho.try_wait(), Ok(Some(_))) {
            break;
        }
        if cfg!(debug_assertions) {
            if parou_em.is_none() && requisicao_http(processo.porta, "GET", "/health", None).is_none()
            {
                parou_em = Some(Instant::now());
            }
            if parou_em.is_some_and(|t| t.elapsed() >= FOLGA_APOS_PARAR) {
                break;
            }
        }
        thread::sleep(Duration::from_millis(50));
    }

    // 3) Força o que tiver sobrado (inclusive processos filhos, via Job Object).
    #[cfg(windows)]
    if let Some(job) = &processo._job {
        job.encerrar_todos();
    }
    let _ = processo.filho.kill();
    let _ = processo.filho.wait();
}

fn porta_livre() -> std::io::Result<u16> {
    // A porta é liberada logo em seguida e usada pelo backend; a janela de corrida
    // é mínima e, se ocorrer, o backend falha ao subir e o usuário pode tentar de novo.
    let ouvinte = TcpListener::bind(("127.0.0.1", 0))?;
    Ok(ouvinte.local_addr()?.port())
}

fn gerar_token() -> Result<String, String> {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes)
        .map_err(|e| format!("Não foi possível gerar o token de sessão: {e}"))?;
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}

fn descrever_saida(status: ExitStatus) -> String {
    match status.code() {
        Some(codigo) => format!("código {codigo}"),
        None => "sem código de saída".into(),
    }
}

/// HTTP/1.1 mínimo só para loopback (evita uma dependência de cliente HTTP).
/// Devolve o status da resposta ou `None` se não conectou.
fn requisicao_http(porta: u16, metodo: &str, caminho: &str, token: Option<&str>) -> Option<u16> {
    let endereco = SocketAddr::from(([127, 0, 0, 1], porta));
    let mut conexao = TcpStream::connect_timeout(&endereco, TIMEOUT_HTTP).ok()?;
    conexao.set_read_timeout(Some(TIMEOUT_HTTP)).ok()?;
    conexao.set_write_timeout(Some(TIMEOUT_HTTP)).ok()?;

    let autorizacao = token
        .map(|t| format!("Authorization: Bearer {t}\r\n"))
        .unwrap_or_default();
    let requisicao = format!(
        "{metodo} {caminho} HTTP/1.1\r\nHost: 127.0.0.1:{porta}\r\n{autorizacao}\
         Content-Length: 0\r\nConnection: close\r\n\r\n"
    );
    conexao.write_all(requisicao.as_bytes()).ok()?;

    let mut buffer = [0u8; 64];
    let lidos = conexao.read(&mut buffer).ok()?;
    let linha = std::str::from_utf8(&buffer[..lidos]).ok()?;
    // Ex.: "HTTP/1.1 200 OK"
    linha.split_whitespace().nth(1)?.parse().ok()
}

/// Aguarda o backend ficar pronto. Rejeita com mensagem em pt-BR se falhar.
#[tauri::command]
pub async fn conexao_backend(
    gerenciador: State<'_, GerenciadorBackend>,
) -> Result<ConexaoBackend, String> {
    let gerenciador = gerenciador.inner().clone();
    loop {
        match gerenciador.estado() {
            Estado::Pronto(conexao) => return Ok(conexao),
            Estado::Falhou(mensagem) => return Err(mensagem),
            Estado::Iniciando => tokio::time::sleep(Duration::from_millis(100)).await,
        }
    }
}

/// Encerra e inicia novamente o backend (botão "Tentar novamente" da UI).
#[tauri::command]
pub async fn reiniciar_backend(gerenciador: State<'_, GerenciadorBackend>) -> Result<(), String> {
    let gerenciador = gerenciador.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        gerenciador.encerrar();
        gerenciador.iniciar();
    })
    .await
    .map_err(|e| format!("Falha ao reiniciar o serviço interno: {e}"))
}
