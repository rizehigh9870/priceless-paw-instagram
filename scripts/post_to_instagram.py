"""
Priceless PAW Instagram 自動投稿スクリプト

仕組み：
1. リポジトリ直下の「インスタ-投稿フォルダ」から、今日の日付(YYYY-MM-DD)で始まるフォルダを探す
2. 見つからなければ何もせず終了（スキップ）
3. 見つかったら、フォルダ内の画像／動画・caption.txt・product_url.txtを読み込む
4. 画像（または動画）をGitHubのRaw URL経由でInstagramに渡し、投稿を作成・公開する
5. 投稿が成功したら、そのフォルダを「■済/YYYY-MM/」配下に移動する（月ごとに整理）

リール（動画）投稿について：
フォルダ内に動画ファイル（.mp4 / .mov）があれば、その日は画像ではなくリールとして投稿する。
動画が無ければ従来どおり画像のカルーセル投稿になるため、
「3日に1回だけリールにする」といった運用は、動画ファイルを置くかどうかだけで切り替えられる。

動画はInstagram側でエンコード処理が走るので、画像のように固定秒数待つのではなく、
コンテナの status_code が FINISHED になるまでポーリングしてから公開する。

★動画の条件（Instagram Graph APIの仕様）：
- 形式: MP4 または MOV（H.264）
- 長さ: 90秒以内（リールタブ掲載を狙うなら5秒以上）
- 比率: 9:16（縦型）を推奨

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
    find_video,
    load_images,
    load_text_file,
    build_raw_url,
    generate_caption,
    log,
    get_today_str,
)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# リール（動画）のエンコード完了を待つ際のポーリング設定
# Metaの推奨は「1分に1回・最大5分」だが、実際は30秒〜2分で完了することが多いため、
# 10秒間隔・最大30回（＝5分）とし、早く終わった時にすぐ公開できるようにしている。
REEL_POLL_INTERVAL_SEC = 10
REEL_MAX_POLL_ATTEMPTS = 30


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


def create_reel_container(video_url: str, caption: str, access_token: str) -> str:
    """
    リール（動画）用のメディアコンテナを作成する。

    画像と違い media_type=REELS と video_url を使う。
    share_to_feed=true にすることで、リールがフィード（プロフィールのグリッド）にも表示される
    ＝従来の画像投稿と同じようにプロフィール上に残るため、運用の見え方が変わらない。
    """
    ig_user_id = os.environ["IG_BUSINESS_ACCOUNT_ID"]
    url = f"{GRAPH_API_BASE}/{ig_user_id}/media"
    payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": access_token,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["id"]


def wait_for_container_ready(creation_id: str, access_token: str) -> bool:
    """
    動画コンテナの処理完了（status_code=FINISHED）を待つ。

    画像は数秒で処理が終わるが、動画はInstagram側でエンコードが走るため
    完了を待たずに publish するとエラーになる。そのため状態をポーリングして待つ。

    Metaの推奨に従い、最大5分・10秒間隔で確認する
    （API呼び出し上限200回/時を浪費しないよう、短すぎる間隔では叩かない）。

    戻り値: 公開可能な状態になったら True、失敗・タイムアウトなら False
    """
    url = f"{GRAPH_API_BASE}/{creation_id}"
    params = {"fields": "status_code,status", "access_token": access_token}

    for attempt in range(REEL_MAX_POLL_ATTEMPTS):
        time.sleep(REEL_POLL_INTERVAL_SEC)

        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status_code = data.get("status_code")

        elapsed = (attempt + 1) * REEL_POLL_INTERVAL_SEC
        log(f"動画の処理状況を確認中（{elapsed}秒経過）: status_code={status_code}")

        if status_code == "FINISHED":
            log("動画の処理が完了しました。公開に進みます。")
            return True
        if status_code == "ERROR":
            log(f"エラー: Instagram側で動画の処理に失敗しました。詳細: {data.get('status')}")
            return False
        # IN_PROGRESS / PUBLISHED 以外はそのまま待機を続ける

    log(f"エラー: 動画の処理が {REEL_MAX_POLL_ATTEMPTS * REEL_POLL_INTERVAL_SEC} 秒以内に完了しませんでした。")
    return False


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

    # 動画があればリール投稿、なければ従来どおり画像投稿に分岐する。
    # 「3日に1回リール」のような運用は、フォルダに動画を置くかどうかだけで切り替わる。
    video = find_video(folder)

    if video is not None:
        log(f"動画ファイルを検出しました: {video.name} → リールとして投稿します。")
        log(f"キャプション {len(caption)} 文字で投稿を作成します。")
        try:
            video_url = build_raw_url(video)
            log(f"動画URL: {video_url}")

            creation_id = create_reel_container(video_url, caption, access_token)
            log(f"リール用メディアコンテナ作成完了: creation_id={creation_id}")

            # 動画はInstagram側のエンコード完了を待ってからでないと公開できない
            if not wait_for_container_ready(creation_id, access_token):
                return 1

            result = publish_container(creation_id, access_token)
            log(f"リール投稿完了！ post_id={result.get('id')}")

        except requests.HTTPError as e:
            log(f"リール投稿でAPIエラーが発生しました: {e}")
            if e.response is not None:
                log(f"レスポンス内容: {e.response.text}")
            return 1

        return 0

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
