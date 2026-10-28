//! Casca desktop do Finanças: só inicialização, ciclo de vida do backend e plugins.
//! Toda regra de negócio fica no backend Python; a interface fica no React.

mod backend;
#[cfg(windows)]
mod job;

use backend::GerenciadorBackend;
use tauri::{Manager, RunEvent};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        // Precisa ser o primeiro plugin: a segunda instância sai antes de iniciar
        // outro backend e apenas traz a janela existente para frente.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(janela) = app.get_webview_window("main") {
                let _ = janela.unminimize();
                let _ = janela.show();
                let _ = janela.set_focus();
            }
        }))
        // Salva e restaura tamanho/posição/maximizado da janela.
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_dialog::init())
        .manage(GerenciadorBackend::default())
        .setup(|app| {
            app.state::<GerenciadorBackend>().iniciar();
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            backend::conexao_backend,
            backend::reiniciar_backend
        ])
        .build(tauri::generate_context!())
        .expect("falha ao inicializar o aplicativo Finanças");

    app.run(|handle, evento| {
        // Fechamento normal: encerra o backend de forma graciosa (e força se preciso).
        if let RunEvent::Exit = evento {
            handle.state::<GerenciadorBackend>().encerrar();
        }
    });
}
