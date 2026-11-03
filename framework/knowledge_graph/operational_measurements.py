"""Small stdlib process measurements, with native Windows working-set counters."""
import os
import platform


def process_memory():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
        counters = Counters(); counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        memory_info = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        memory_info.restype = wintypes.BOOL
        if not memory_info(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError("process_memory_query_failed")
        return {"working_set_bytes": counters.WorkingSetSize, "peak_working_set_bytes": counters.PeakWorkingSetSize,
                "private_bytes": counters.PrivateUsage, "method": "Windows_GetProcessMemoryInfo"}
    import resource
    usage = resource.getrusage(resource.RUSAGE_SELF)
    scale = 1 if platform.system() == "Darwin" else 1024
    return {"peak_working_set_bytes": usage.ru_maxrss*scale, "method": "getrusage_peak_RSS"}
