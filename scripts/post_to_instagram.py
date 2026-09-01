"""
Priceless PAW Instagram 自動投稿スクリプト

仕組み：
1. リポジトリ直下の「インスタ-投稿フォルダ」から、今日の日付(YYYY-MM-DD)で始まるフォルダを探す
2. 見つからなければ何もせず終了（スキップ）
3. 見つかったら、フォルダ内の画像・caption.txt・product_url.txtを読み込む
4. 画像をGitHubのRaw URL経由でInstagramに渡し、投稿を作成・公開する
5. 投稿が成功したら、そのフォルダを「■済/YYYY-MM/」配下に移動する（月ごとに整理）

必要な環境変数（GitHub Actions の Secrets から渡される）:
- IG_ACCESS_TOKEN         : Instagram Graph API アクセストークン
- IG_BUSINESS_ACCOUNT_ID  : InstagramビジネスアカウントID
- GITHUB_REPOSITORY       : "owner/repo" 形式（GitHub Actionsが自動で渡す）
"""

import os
import sys
import time
import shutil
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
# 設定
# ============================================================
REPO_ROOT = Path(__file__).resolve().parent.parent  # priceless-paw-instagram（リポジトリルート）
BASE_DIR = REPO_ROOT / "インスタ-投稿フォルダ"
DONE_DIR = BASE_DIR / "■済"
GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

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
    from urllib.parse import quote
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


def create_media_container(image_url: str, is_carousel_item: bool, access_token: str) -> str:
    """1枚の画像に対してメディアコンテナを作成し、コンテナIDを返す"""
    ig_user_id = os.environ["IG_BUSINESS_ACCOUNT_ID"]
    url = f"{GRAPH_API_BASE}/{ig_user_id}/media"
    payload = {
        "image_url": image_url,
        "access_token": access_token,
    }
    if is_carousel_item:
        payload["is_carousel_item"] = "true"

    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["id"]


def create_carousel_container(children_ids: list[str], caption: str, access_token: str) -> str:
    """複数枚の画像をまとめたカルーセルコンテナを作成する"""
    ig_user_id = os.environ["IG_BUSINESS_ACCOUNT_ID"]
    url = f"{GRAPH_API_BASE}/{ig_user_id}/media"
    payload = {
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": caption,
        "access_token": access_token,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["id"]


def create_single_container(image_url: str, caption: str, access_token: str) -> str:
    """画像1枚だけの投稿コンテナを作成する"""
    ig_user_id = os.environ["IG_BUSINESS_ACCOUNT_ID"]
    url = f"{GRAPH_API_BASE}/{ig_user_id}/media"
    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["id"]


def publish_container(creation_id: str, access_token: str) -> dict:
    ig_user_id = os.environ["IG_BUSINESS_ACCOUNT_ID"]
    url = f"{GRAPH_API_BASE}/{ig_user_id}/media_publish"
    payload = {
        "creation_id": creation_id,
        "access_token": access_token,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


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


def main() -> int:
    access_token = os.environ.get("IG_ACCESS_TOKEN")
    if not access_token:
        log("エラー: 環境変数 IG_ACCESS_TOKEN が設定されていません")
        return 1

    folder = find_today_folder()
    if folder is None:
        log(f"今日({get_today_str()})の投稿対象フォルダが見つかりません。スキップします。")
        return 0

    log(f"投稿対象フォルダを発見: {folder.name}")

    product_url_path = folder / "product_url.txt"
    caption_path = folder / "caption.txt"

    product_url = load_text_file(product_url_path)
    if not product_url:
        log(f"エラー: {product_url_path} が存在しないか空です。投稿を中止します。")
        return 1

    caption = load_text_file(caption_path)
    if not caption:
        log("caption.txt が見つからないため、簡易キャプションを自動生成します。")
        caption = generate_caption(product_url)

    images = load_images(folder)
    if not images:
        log(f"エラー: {folder} に画像ファイルが見つかりません。投稿を中止します。")
        return 1

    log(f"画像 {len(images)} 枚、キャプション {len(caption)} 文字で投稿を作成します。")

    try:
        if len(images) == 1:
            image_url = build_raw_url(images[0])
            log(f"画像URL: {image_url}")
            creation_id = create_single_container(image_url, caption, access_token)
        else:
            children_ids = []
            for image_path in images:
                image_url = build_raw_url(image_path)
                log(f"画像URL: {image_url}")
                child_id = create_media_container(image_url, is_carousel_item=True, access_token=access_token)
                children_ids.append(child_id)
                time.sleep(1)  # API負荷軽減のための小休止
            creation_id = create_carousel_container(children_ids, caption, access_token)

        log(f"メディアコンテナ作成完了: creation_id={creation_id}")

        # コンテナがInstagram側で処理されるまで少し待つ
        time.sleep(5)

        result = publish_container(creation_id, access_token)
        log(f"投稿完了！ post_id={result.get('id')}")

    except requests.HTTPError as e:
        log(f"APIエラーが発生しました: {e}")
        if e.response is not None:
            log(f"レスポンス内容: {e.response.text}")
        return 1

    move_to_done(folder)
    return 0


if __name__ == "__main__":
    sys.exit(main())
