// Em release, não abre janela de console junto com o app no Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    financas_lib::run()
}
