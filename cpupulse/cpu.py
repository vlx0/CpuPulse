"""CPU load via Win32. No extra packages."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import winreg
from dataclasses import dataclass

ntdll = ctypes.windll.ntdll
kernel32 = ctypes.windll.kernel32

SystemProcessorPerformanceInformation = 8
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]


class SYSTEM_PROCESSOR_PERFORMANCE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("IdleTime", ctypes.c_int64),
        ("KernelTime", ctypes.c_int64),
        ("UserTime", ctypes.c_int64),
        ("DpcTime", ctypes.c_int64),
        ("InterruptTime", ctypes.c_int64),
        ("InterruptCount", wt.ULONG),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", wt.WCHAR * 260),
    ]


def _ft(t: FILETIME) -> int:
    return (int(t.dwHighDateTime) << 32) | int(t.dwLowDateTime)


def cpu_name() -> str:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        )
        name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        winreg.CloseKey(key)
        return str(name).strip()
    except OSError:
        return "CPU"


def nproc() -> int:
    fn = getattr(kernel32, "GetActiveProcessorCount", None)
    if fn is not None:
        n = int(fn(0xFFFF) or 0)
        if n > 0:
            return n
    return max(1, int(os.cpu_count() or 1))


def sample_times() -> tuple[int, int]:
    idle = FILETIME()
    kernel = FILETIME()
    user = FILETIME()
    if not kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return 0, 0
    i, k, u = _ft(idle), _ft(kernel), _ft(user)
    total = k + u
    busy = (k - i) + u
    return busy, total


def sample_cores() -> list[tuple[int, int]]:
    n = nproc()
    arr = (SYSTEM_PROCESSOR_PERFORMANCE_INFORMATION * n)()
    size = ctypes.sizeof(arr)
    ret = ntdll.NtQuerySystemInformation(SystemProcessorPerformanceInformation, ctypes.byref(arr), size, None)
    if ret != 0:
        return []
    out: list[tuple[int, int]] = []
    for i in range(n):
        p = arr[i]
        idle = int(p.IdleTime)
        kernel = int(p.KernelTime)
        user = int(p.UserTime)
        total = kernel + user
        busy = (kernel - idle) + user
        out.append((busy, total))
    return out


def _process_times(pid: int) -> int | None:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        ctime = FILETIME()
        etime = FILETIME()
        ktime = FILETIME()
        utime = FILETIME()
        if not kernel32.GetProcessTimes(
            h, ctypes.byref(ctime), ctypes.byref(etime), ctypes.byref(ktime), ctypes.byref(utime)
        ):
            return None
        return _ft(ktime) + _ft(utime)
    finally:
        kernel32.CloseHandle(h)


def list_processes() -> dict[int, tuple[str, int]]:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE or not snap:
        return {}
    out: dict[int, tuple[str, int]] = {}
    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    try:
        if not kernel32.Process32FirstW(snap, ctypes.byref(pe)):
            return {}
        while True:
            pid = int(pe.th32ProcessID)
            if pid:
                used = _process_times(pid)
                if used is not None:
                    out[pid] = (pe.szExeFile, used)
            if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                break
    finally:
        kernel32.CloseHandle(snap)
    return out


@dataclass
class CpuSnap:
    total_pct: float
    cores: list[float]
    top: list[tuple[str, int, float]]
    name: str
    nproc: int


class CpuSampler:
    def __init__(self) -> None:
        self.name = cpu_name()
        self.n = nproc()
        self._busy, self._total = sample_times()
        self._cores = sample_cores()
        self._procs = list_processes()
        self._proc_total = self._total
        self._top: list[tuple[str, int, float]] = []

    def tick(self) -> CpuSnap:
        busy, total = sample_times()
        db, dt = busy - self._busy, total - self._total
        self._busy, self._total = busy, total
        total_pct = 0.0 if dt <= 0 else max(0.0, min(100.0, 100.0 * db / dt))

        cores_now = sample_cores()
        cores_pct: list[float] = []
        if cores_now and self._cores and len(cores_now) == len(self._cores):
            for (b0, t0), (b1, t1) in zip(self._cores, cores_now):
                dtt = t1 - t0
                cores_pct.append(0.0 if dtt <= 0 else max(0.0, min(100.0, 100.0 * (b1 - b0) / dtt)))
        self._cores = cores_now or self._cores
        return CpuSnap(total_pct, cores_pct, self._top, self.name, self.n)

    def sample_top(self) -> list[tuple[str, int, float]]:
        now = list_processes()
        _, total = sample_times()
        pdt = total - self._proc_total
        top: list[tuple[str, int, float]] = []
        if pdt > 0:
            for pid, (exe, used) in now.items():
                prev = self._procs.get(pid)
                if not prev:
                    continue
                d = used - prev[1]
                if d <= 0:
                    continue
                pct = 100.0 * d / pdt
                top.append((exe, pid, max(0.0, min(100.0, pct))))
        top.sort(key=lambda x: x[2], reverse=True)
        self._procs = now
        self._proc_total = total
        self._top = top[:10]
        return self._top
