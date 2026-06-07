# -*- coding: utf-8 -*-
"""
抖净 DouClean — 更新器
由主程序在发现新版本后调用: python updater.py <zip路径>
"""
import sys, os, time, shutil, zipfile, subprocess
from pathlib import Path

EXE_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
BACKUP_DIR = EXE_DIR / "_old_backup"
KEEP_FILES = ["data", "output", "settings.json", ".douclean.lock"]


def run(zip_path: str, restart=True):
    zip_file = Path(zip_path)
    if not zip_file.exists():
        print(f"zip 不存在: {zip_file}")
        return False

    print("[updater] 开始更新...")
    time.sleep(1)  # 等主程序退出

    # 1. 备份旧数据
    backup_data = {}
    for item in KEEP_FILES:
        src = EXE_DIR / item
        if src.exists():
            dst = BACKUP_DIR / item
            if src.is_dir():
                if dst.exists(): shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
                print(f"[updater] 备份: {item}/")
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                print(f"[updater] 备份: {item}")
            backup_data[item] = True

    # 2. 解压新版本
    try:
        with zipfile.ZipFile(zip_file, 'r') as z:
            for member in z.namelist():
                # zip 内第一个文件夹是 抖净/ → 去掉前缀
                parts = member.split('/', 1)
                if len(parts) > 1:
                    target = EXE_DIR / parts[1]
                else:
                    continue
                if member.endswith('/'):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src, open(target, 'wb') as dst:
                        dst.write(src.read())
        print("[updater] 解压完成")
    except Exception as e:
        print(f"[updater] 解压失败: {e}")
        return False

    # 3. 恢复数据
    for item, _ in backup_data.items():
        src = BACKUP_DIR / item
        dst = EXE_DIR / item
        if src.is_dir():
            if dst.exists(): shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
            print(f"[updater] 恢复: {item}/")
        elif src.exists():
            shutil.copy2(src, dst)
            print(f"[updater] 恢复: {item}")

    # 4. 清理
    shutil.rmtree(BACKUP_DIR, ignore_errors=True)
    zip_file.unlink(missing_ok=True)
    print("[updater] 更新完成")

    # 5. 重启
    if restart:
        exe = EXE_DIR / "抖净.exe"
        if exe.exists():
            time.sleep(0.5)
            subprocess.Popen([str(exe)], cwd=str(EXE_DIR))
            print("[updater] 已启动新版本")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: updater.py <zip路径>")
        sys.exit(1)
    run(sys.argv[1])
