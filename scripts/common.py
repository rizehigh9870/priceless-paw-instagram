"""
Priceless PAW 自動投稿 共通処理

post_to_instagram.py と post_to_threads.py の両方から使う共通のユーティリティ関数群。
- 今日の投稿対象フォルダの探索
- 画像・キャプション・商品URLの読み込み
- 画像のGitHub Raw URL組み立て
- 投稿完了フォルダの移動
- ログ出力
"""

import os
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote

# ============================================================
# 設定
# ============================================================
REPO_ROOT = Path(__file__).resolve().parent.parent  # priceless-paw-instagram（リポジトリルート）
BASE_DIR = REPO_ROOT / "インスタ-投稿フォルダ"
DONE_DIR = BASE_DIR / "■済"
LOG_DIR = REPO_ROOT / "log"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# 日本時間(JST)で「今日」の日付を取得する
JST = timezone(timedelta(hours=9))


def log(message: str) -> None:
    timestamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def get_today_str() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def find_today_folder() -> Path | None:
    """今日の日付で始まるフォルダを「インスタ-投稿フォルダ」直下から探す"""
    today = get_today_str()
    for entry in sorted(BASE_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name == "■済":
            continue
        if entry.name.startswith(today):
            return entry
    return None


def load_images(folder: Path) -> list[Path]:
    """フォルダ内の画像ファイルをファイル名の昇順で取得"""
    images = [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(images, key=lambda p: p.name)


def load_text_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def build_raw_url(image_path: Path) -> str:
    """GitHubリポジトリ上のRaw URLを組み立てる（リポジトリルートからの相対パスを使う）"""
    repo = os.environ["GITHUB_REPOSITORY"]  # 例: rizehigh9870/priceless-paw-instagram
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    rel_path = image_path.relative_to(REPO_ROOT).as_posix()
    encoded_path = quote(rel_path)
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{encoded_path}"


def generate_caption(product_url: str) -> str:
    """
    caption.txt が無い場合の簡易フォールバック。
    本来は商品ページの情報を取得して生成するのが望ましいが、
    最低限のフォールバックとして商品URLのみ案内する文言を返す。
    """
    return (
        "🐾Priceless PAWからの新着アイテムです🐾\n\n"
        "詳しくはプロフィールのリンクからショップをご覧ください🔍\n\n"
        f"{product_url}\n\n"
        "#PricelessPAW"
    )


def append_daily_log(content: str, result: str, next_action: str, folder_name: str | None = None) -> None:
    """
    AIカンパニー構想の申し送りログに1日1エントリを追記する（/log/YYYY-MM.md、追記のみ）。

    「ログ追記が終わるまでタスク完了とみなさない」という完了条件の実体がこの関数。
    daily_post.yml の最後で必ず呼ばれる想定。

    引数:
        content: 「内容」欄に書く1行（例: 対象フォルダ名や投稿商品名）
        result: 「結果」欄に書く1行（例: "Instagram成功 / Threads成功"）
        next_action: 「次に必要なこと」欄に書く1行（無ければ "なし"）
        folder_name: 見出しに添える補足（省略時は content をそのまま使う）
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(JST)
    log_path = LOG_DIR / f"{today.strftime('%Y-%m')}.md"

    heading_suffix = f" {folder_name}" if folder_name else ""
    entry = (
        f"## {today.strftime('%Y-%m-%d')} 投稿{heading_suffix}\n"
        f"- 内容: {content}\n"
        f"- 結果: {result}\n"
        f"- 次に必要なこと: {next_action}\n\n"
    )

    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)

    log(f"申し送りログに追記しました: {log_path}")


def move_to_done(folder: Path) -> None:
    """投稿完了フォルダを ■済/YYYY-MM/ 配下へ移動する（月ごとに整理）"""
    # フォルダ名の先頭7文字（YYYY-MM）を月別サブフォルダ名として使う
    month_dir = DONE_DIR / folder.name[:7]
    month_dir.mkdir(parents=True, exist_ok=True)
    destination = month_dir / folder.name
    if destination.exists():
        log(f"警告: 移動先に同名フォルダが既に存在するため移動をスキップします: {destination}")
        return
    shutil.move(str(folder), str(destination))
    log(f"投稿完了フォルダを移動しました: {destination}")
