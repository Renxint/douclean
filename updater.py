# -*- coding: utf-8 -*-
"""
抖净 DouClean — 更新器
由主程序在发现新版本后调用: python updater.py <zip路径>

策略：先解压到临时目录 → 重命名旧目录 → 移动新目录 → 恢复数据 → 重启
"""
import sys, os, time, shutil, zipfile, subprocess
from pathlib import Path

EXE_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
KEEP_ITEMS = ["data", "output", "settings.json"]


def _retry_remove(path: Path, max_tries=5):
    """重试删除（处理文件锁定）"""
    for i in range(max_tries):
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink()
            return
        except PermissionError:
            time.sleep(1)
    # 最后一次：重命名后标记删除
    try:
        if path.exists():
            tmp = path.with_name(path.name + "_old_" + str(int(time.time())))
            path.rename(tmp)
    except Exception:
        pass


def run(zip_path: str, restart=True):
    zip_file = Path(zip_path)
    if not zip_file.exists():
        print(f"[updater] zip 不存在: {zip_file}")
        return False

    print("[updater] 等待主程序退出...")
    time.sleep(2)

    # 1. 解压到临时目录
    tmp_dir = EXE_DIR / "_update_tmp"
    _retry_remove(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_file, 'r') as z:
            for member in z.namelist():
                parts = member.split('/', 1)
                if len(parts) < 2: continue
                target = tmp_dir / parts[1]
                if member.endswith('/'):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src, open(target, 'wb') as dst:
                        dst.write(src.read())
        print("[updater] 解压完成")
    except Exception as e:
        print(f"[updater] 解压失败: {e}")
        _retry_remove(tmp_dir)
        return False

    # 2. 复制数据文件到临时目录（与新版合并）
    for item in KEEP_ITEMS:
        src = EXE_DIR / item
        dst = tmp_dir / item
        if not src.exists(): continue
        if src.is_dir():
            if dst.exists():
                # 合并目录：只复制旧版独有的文件
                for f in src.rglob('*'):
                    rel = f.relative_to(src)
                    df = dst / rel
                    if not df.exists():
                        df.parent.mkdir(parents=True, exist_ok=True)
                        if f.is_file():
                            shutil.copy2(f, df)
            else:
                shutil.copytree(src, dst)
            print(f"[updater] 保留数据: {item}/")
        else:
            # 文件：新版有则跳过，无则复制
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            print(f"[updater] 保留: {item}")

    # 3. 重命名旧目录 → 移动新目录
    old_dir = EXE_DIR.with_name(EXE_DIR.name + "_old_" + str(int(time.time())))
    try:
        EXE_DIR.rename(old_dir)
        print("[updater] 旧版本已备份")
    except Exception as e:
        print(f"[updater] 重命名失败: {e}")
        _retry_remove(tmp_dir)
        return False

    try:
        tmp_dir.rename(EXE_DIR)
        print("[updater] 新版本就位")
    except Exception:
        # 移动失败，回滚
        old_dir.rename(EXE_DIR)
        _retry_remove(tmp_dir)
        return False

    # 4. 清理
    zip_file.unlink(missing_ok=True)
    _retry_remove(old_dir)

    # 5. 重启
    if restart:
        exe = EXE_DIR / "抖净.exe"
        if exe.exists():
            subprocess.Popen([str(exe)], cwd=str(EXE_DIR))
            print("[updater] 已启动新版本")

    print("[updater] 更新完成")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: updater.py <zip路径>")
        sys.exit(1)
    run(sys.argv[1])
