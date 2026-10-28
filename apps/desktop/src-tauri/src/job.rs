//! Job Object do Windows: amarra o backend (e os filhos dele) ao app.
//!
//! Com `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, quando o último handle do job é fechado
//! (inclusive se o app for finalizado à força pelo Gerenciador de Tarefas), o Windows
//! encerra todos os processos do job. Isso evita backends órfãos.

use std::ffi::c_void;
use std::io;
use std::mem::{size_of, zeroed};
use std::os::windows::io::AsRawHandle;
use std::process::Child;
use std::ptr::null;

use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, TerminateJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};

pub struct JobObject(HANDLE);

// O handle do job pode ser usado de qualquer thread (APIs do Windows são thread-safe).
unsafe impl Send for JobObject {}
unsafe impl Sync for JobObject {}

impl JobObject {
    pub fn criar() -> io::Result<Self> {
        // SAFETY: parâmetros nulos são permitidos (atributos padrão, job sem nome).
        let handle = unsafe { CreateJobObjectW(null(), null()) };
        if handle.is_null() {
            return Err(io::Error::last_os_error());
        }
        let job = JobObject(handle);

        // SAFETY: estrutura C simples; zero é um valor válido para todos os campos.
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { zeroed() };
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        // SAFETY: ponteiro e tamanho apontam para `info`, válida durante a chamada.
        let ok = unsafe {
            SetInformationJobObject(
                job.0,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const c_void,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        };
        if ok == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(job)
    }

    pub fn associar(&self, filho: &Child) -> io::Result<()> {
        // SAFETY: o handle do processo filho é válido enquanto `filho` existir.
        let ok = unsafe { AssignProcessToJobObject(self.0, filho.as_raw_handle() as HANDLE) };
        if ok == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(())
    }

    /// Encerra imediatamente todos os processos do job (inclui netos, como o
    /// worker do uvicorn em modo reload).
    pub fn encerrar_todos(&self) {
        // SAFETY: handle válido até o Drop.
        unsafe {
            TerminateJobObject(self.0, 1);
        }
    }
}

impl Drop for JobObject {
    fn drop(&mut self) {
        // SAFETY: handle criado por CreateJobObjectW e fechado uma única vez.
        unsafe {
            CloseHandle(self.0);
        }
    }
}
