import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows scheduler class")
def test_live_priority_is_above_normal_without_changing_parent_priority():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32")
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetPriorityClass.argtypes = (wintypes.HANDLE,)
    kernel.GetPriorityClass.restype = wintypes.DWORD
    before = kernel.GetPriorityClass(kernel.GetCurrentProcess())
    child = """from fortnite_chest_counter import paths
import ctypes
from ctypes import wintypes
assert paths.prefer_detector_cpu()
k = ctypes.WinDLL('kernel32')
k.GetCurrentProcess.restype = wintypes.HANDLE
k.GetPriorityClass.argtypes = (wintypes.HANDLE,)
k.GetPriorityClass.restype = wintypes.DWORD
assert k.GetPriorityClass(k.GetCurrentProcess()) == 0x8000
"""
    subprocess.run([sys.executable, "-c", child], check=True, timeout=15)
    assert kernel.GetPriorityClass(kernel.GetCurrentProcess()) == before
