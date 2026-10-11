"""Minimal ctypes binding to hivex, preserving values outside requested edits."""
import ctypes as C
import ctypes.util
import errno
import os
from pathlib import Path


class SetValue(C.Structure):
    _fields_ = [("key", C.c_char_p), ("type", C.c_int),
                ("length", C.c_size_t), ("data", C.c_void_p)]


class Hive:
    def __init__(self, path, write=False):
        library = ctypes.util.find_library("hivex")
        if not library:
            for candidate in ("/opt/homebrew/lib/libhivex.dylib", "/usr/local/lib/libhivex.dylib"):
                if Path(candidate).exists():
                    library = candidate
                    break
        if not library:
            raise RuntimeError("libhivex not found; install it with brew install hivex")
        self.lib = C.CDLL(library, use_errno=True)
        self.libc = C.CDLL(None)
        self.libc.free.argtypes = [C.c_void_p]
        signatures = {
            "open": ([C.c_char_p, C.c_int], C.c_void_p),
            "close": ([C.c_void_p], C.c_int),
            "root": ([C.c_void_p], C.c_size_t),
            "node_get_child": ([C.c_void_p, C.c_size_t, C.c_char_p], C.c_size_t),
            "node_add_child": ([C.c_void_p, C.c_size_t, C.c_char_p], C.c_size_t),
            "node_delete_child": ([C.c_void_p, C.c_size_t], C.c_int),
            "node_get_value": ([C.c_void_p, C.c_size_t, C.c_char_p], C.c_size_t),
            "node_set_value": ([C.c_void_p, C.c_size_t, C.POINTER(SetValue), C.c_int], C.c_int),
            "value_value": ([C.c_void_p, C.c_size_t, C.POINTER(C.c_int), C.POINTER(C.c_size_t)], C.c_void_p),
            "commit": ([C.c_void_p, C.c_char_p, C.c_int], C.c_int),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.lib, "hivex_" + name)
            fn.argtypes, fn.restype = args, result
        self.handle = self.lib.hivex_open(os.fsencode(path), 4 if write else 0)
        if not self.handle:
            self.error("open hive")

    def error(self, operation):
        raise RuntimeError(f"hivex {operation}: {os.strerror(C.get_errno())}")

    def node(self, path, create=False):
        node = self.lib.hivex_root(self.handle)
        if not node:
            self.error("root")
        for part in path.strip("\\").split("\\") if path.strip("\\") else []:
            C.set_errno(0)
            child = self.lib.hivex_node_get_child(self.handle, node, part.encode())
            if not child:
                if C.get_errno() not in (0, errno.ENOENT):
                    self.error("find child")
                if not create:
                    return 0
                child = self.lib.hivex_node_add_child(self.handle, node, part.encode())
                if not child:
                    self.error("add child")
            node = child
        return node

    def read(self, path, name):
        node = self.node(path)
        if not node:
            return None
        value = self.lib.hivex_node_get_value(self.handle, node, name.encode())
        if not value:
            return None
        kind, length = C.c_int(), C.c_size_t()
        ptr = self.lib.hivex_value_value(self.handle, value, C.byref(kind), C.byref(length))
        if not ptr:
            self.error("read value")
        try:
            return kind.value, C.string_at(ptr, length.value)
        finally:
            self.libc.free(ptr)

    @staticmethod
    def encode(kind, value):
        if kind == "REG_DWORD":
            return 4, int(value).to_bytes(4, "little")
        if kind == "REG_SZ":
            return 1, (str(value) + "\0").encode("utf-16-le")
        raise RuntimeError(f"Unsupported registry type {kind}")

    def set(self, path, name, kind, value):
        node = self.node(path, create=True)
        registry_type, data = self.encode(kind, value)
        buffer = C.create_string_buffer(data)
        pair = SetValue(name.encode(), registry_type, len(data), C.cast(buffer, C.c_void_p))
        if self.lib.hivex_node_set_value(self.handle, node, C.byref(pair), 0) == -1:
            self.error("set value")
        if self.read(path, name) != (registry_type, data):
            raise RuntimeError(f"Registry read-back mismatch at {path}\\{name}")

    def delete(self, path):
        node = self.node(path)
        if node and self.lib.hivex_node_delete_child(self.handle, node) == -1:
            self.error("delete key")
        if self.node(path):
            raise RuntimeError(f"Registry key still exists after deletion: {path}")

    def commit(self, destination):
        if self.lib.hivex_commit(self.handle, os.fsencode(destination), 0) == -1:
            self.error("commit")

    def close(self):
        if self.handle:
            result = self.lib.hivex_close(self.handle)
            self.handle = None
            if result == -1:
                self.error("close")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
