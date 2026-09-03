"""
Priceless PAW Threads 自動投稿スクリプト

なぜこのスクリプトが必要か：
Instagramアプリ/Web管理画面から手動で投稿した場合、「シェア先」設定がONならThreadsへ
自動でクロスポストされる。しかしこれはInstagramアプリ側のUI機能であり、
Instagram Graph API経由の投稿（post_to_instagram.py）はこのクロスポスト機能の対象外。
そのため、Threads API（graph.threads.net）を使って別途明示的に投稿する。

仕組み：
1. post_to_instagram.py と同じ「今日のフォルダ」を探す
   （post_to_instagram.py はフォルダを移動しないので、このスクリプトも読み取れる）
2. 見つからなければ何もせず終了（スキップ）
3. フォルダ内の画像・caption.txt・product_url.txtを読み込む（post_to_instagram.pyと同じロジック）
4. 画像をGitHubのRaw URL経由でThreadsに渡し、投稿を作成・公開する

必要な環境変数（GitHub Actions の Secrets から渡される）:
- THREADS_ACCESS_TOKEN    : Threads API アクセストークン
- THREADS_USER_ID         : Threads ユーザーID
- GITHUB_REPOSITORY       : "owner/repo" 形式（GitHub Actionsが自動で渡す）

THREADS_ACCESS_TOKEN / THREADS_USER_ID が未設定の場合は、
Threads APIの準備がまだ整っていないとみなし、エラーにせず静かにスキップする
（Instagram投稿の運用を止めないため）。

投稿完了フォルダの「■済」への移動はこのスクリプトでは行わない
（post_to_instagram.py → post_to_threads.py の両方が終わった後、
  move_completed_folder.py が一括で移動する）。
"""

import sys
import time
import requests
import os

from common import (
    find_today_folder,
    load_images,
    load_text_file,
    build_raw_url,
    generate_caption,
    log,
    get_today_str,
)

THREADS_API_VERSION = "v1.0"
THREADS_API_BASE = f"https://graph.threads.net/{THREADS_API_VERSION}"


def create_media_container(
    image_url: str,
    access_token: str,
    threads_user_id: str,
    is_carousel_item: bool = False,
    caption: str | None = None,
) -> str:
    """Threads用のメディアコンテナ（画像1点分）を作成し、コンテナIDを返す"""
    url = f"{THREADS_API_BASE}/{threads_user_id}/threads"
    payload = {
        "media_type": "IMAGE",
        "image_url": image_url,
        "access_token": access_token,
    }
    if is_carousel_item:
        payload["is_carousel_item"] = "true"
    if caption:
        payload["text"] = caption

    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["id"]


def create_carousel_container(
    children_ids: list[str], caption: str, access_token: str, threads_user_id: str
) -> str:
    """Threads用のカルーセルコンテナを作成する"""
    url = f"{THREADS_API_BASE}/{threads_user_id}/threads"
    payload = {
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "text": caption,
        "access_token": access_token,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["id"]


def publish_container(creation_id: str, access_token: str, threads_user_id: str) -> dict:
    url = f"{THREADS_API_BASE}/{threads_user_id}/threads_publish"
    payload = {
        "creation_id": creation_id,
        "access_token": access_token,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    access_token = os.environ.get("THREADS_ACCESS_TOKEN")
    threads_user_id = os.environ.get("THREADS_USER_ID")

    if not access_token or not threads_user_id:
        log("THREADS_ACCESS_TOKEN / THREADS_USER_ID が未設定のため、Threadsへの投稿はスキップします。")
        return 0

    folder = find_today_folder()
    if folder is None:
        log(f"今日({get_today_str()})の投稿対象フォルダが見つかりません。スキップします。")
        return 0

    log(f"投稿対象フォルダを発見: {folder.name}")

    product_url_path = folder / "product_url.txt"
    caption_path = folder / "caption.txt"

    product_url = load_text_file(product_url_path)
    if not product_url:
        log(f"エラー: {product_url_path} が存在しないか空です。Threads投稿を中止します。")
        return 1

    caption = load_text_file(caption_path)
    if not caption:
        log("caption.txt が見つからないため、簡易キャプションを自動生成します。")
        caption = generate_caption(product_url)

    images = load_images(folder)
    if not images:
        log(f"エラー: {folder} に画像ファイルが見つかりません。Threads投稿を中止します。")
        return 1

    log(f"画像 {len(images)} 枚、キャプション {len(caption)} 文字でThreads投稿を作成します。")

    try:
        if len(images) == 1:
            image_url = build_raw_url(images[0])
            log(f"画像URL: {image_url}")
            creation_id = create_media_container(
                image_url, access_token, threads_user_id, caption=caption
            )
        else:
            children_ids = []
            for image_path in images:
                image_url = build_raw_url(image_path)
                log(f"画像URL: {image_url}")
                child_id = create_media_container(
                    image_url, access_token, threads_user_id, is_carousel_item=True
                )
                children_ids.append(child_id)
                time.sleep(1)  # API負荷軽減のための小休止
            creation_id = create_carousel_container(
                children_ids, caption, access_token, threads_user_id
            )

        log(f"Threadsメディアコンテナ作成完了: creation_id={creation_id}")

        # コンテナがThreads側で処理されるまで少し待つ
        time.sleep(5)

        result = publish_container(creation_id, access_token, threads_user_id)
        log(f"Threads投稿完了！ threads_post_id={result.get('id')}")

    except requests.HTTPError as e:
        log(f"Threads投稿でAPIエラーが発生しました: {e}")
        if e.response is not None:
            log(f"レスポンス内容: {e.response.text}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
