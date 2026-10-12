"""Installer: build the zipapp, pin its hash into the hook entries, write both hook layers, keep a registry."""

import os
import shutil
import zipapp

from . import VERSION, canon, integrity, ledger as ledger_mod, paths


def registry_path():
    return os.path.join(paths.home(), "registry.json")


def load_registry():
    p = registry_path()
    if not os.path.exists(p):
        return {"workspaces": []}
    return integrity.read_json(p)


def save_registry(reg):
    integrity.write_json(registry_path(), reg)


def register_workspace(root):
    reg = load_registry()
    root = os.path.realpath(root)
    if root not in reg["workspaces"]:
        reg["workspaces"].append(root)
        save_registry(reg)


def build_pyz(src_dir, target=None):
    """Build ~/.g1/g1.pyz from the package source directory (the directory containing g1/).
    The archive holds bytecode only (no source compile at hook time; measured 15-25 ms faster per hook)."""
    import compileall
    import tempfile
    paths.ensure_dirs()
    target = target or paths.pyz_path()
    stage = tempfile.mkdtemp(prefix="g1-build-", dir=paths.home())
    try:
        shutil.copytree(os.path.join(src_dir, "g1"), os.path.join(stage, "g1"),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        if not compileall.compile_dir(os.path.join(stage, "g1"), quiet=1, legacy=True):
            raise RuntimeError("bytecode compilation failed")
        for dp, dns, fns in os.walk(stage):
            for fn in fns:
                if fn.endswith(".py"):
                    os.unlink(os.path.join(dp, fn))
        tmp = target + ".tmp"
        zipapp.create_archive(stage, tmp, interpreter=None, main="g1.__main__:main", compressed=True)
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return canon.sha256_file(target)


def global_hooks_path():
    from .adapter import agy
    return agy.global_hooks_path()


def install(src_dir, with_global=True, workspaces=None):
    from .adapter import agy
    paths.ensure_dirs()
    pin = build_pyz(src_dir)
    gpath = global_hooks_path()
    manifest = integrity.make_manifest(pin, gpath, with_global, agy.TOOL_MATCHER)
    backups = {}
    if with_global:
        backups[gpath] = integrity.install_group(gpath, manifest["group"])
    reg = load_registry()
    for root in list(reg["workspaces"]) + list(workspaces or []):
        hp = os.path.join(root, ".agents", "hooks.json")
        if not os.path.isdir(root):
            continue
        if with_global:
            integrity.remove_group(hp)  # one layer only: the global root of trust
        else:
            backups[hp] = integrity.install_group(hp, manifest["group"])
    manifest["backups"] = backups
    manifest["host_fingerprint"] = agy.host_fingerprint()
    manifest["host_verified_at"] = manifest["installed_at"]
    if with_global:
        manifest["host_files"] = integrity.install_host_files(agy.config_root())
    integrity.save_manifest(manifest)
    return manifest


def host_verify():
    """Record the running host binary as the measured one (run after re-running the probe suite)."""
    from .adapter import agy
    m = integrity.load_manifest()
    if not m:
        raise RuntimeError("G1 is not installed")
    m["host_fingerprint"] = agy.host_fingerprint()
    m["host_verified_at"] = integrity.ledger_mod.now_iso()
    integrity.save_manifest(m)
    return m["host_fingerprint"]


def uninstall(purge=False):
    removed = []
    gpath = global_hooks_path()
    if integrity.remove_group(gpath):
        removed.append(gpath)
    reg = load_registry()
    for root in reg["workspaces"]:
        hp = os.path.join(root, ".agents", "hooks.json")
        if integrity.remove_group(hp):
            removed.append(hp)
    from .adapter import agy
    removed += integrity.remove_host_files(agy.config_root())
    if purge:
        shutil.rmtree(paths.home(), ignore_errors=True)
    else:
        mp = paths.manifest_path()
        if os.path.exists(mp):
            os.unlink(mp)
    return removed
