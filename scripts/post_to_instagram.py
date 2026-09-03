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

Threadsへの投稿について：
Instagram投稿は「シェア先」設定でアプリ/Web UIから投稿した場合のみThreadsへ自動クロスポストされる。
Graph API（本スクリプト）経由の投稿にはこのクロスポスト機能が適用されないため、
Threadsへの投稿は別スクリプト（post_to_threads.py）が担当する。

本スクリプトは投稿完了フォルダの「■済」への移動を行わない
（daily_post.yml で post_to_instagram.py → post_to_threads.py → move_completed_folder.py
  の順に実行し、両方の投稿処理が終わった後にまとめて移動する）。
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

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


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

    return 0


if __name__ == "__main__":
    sys.exit(main())
