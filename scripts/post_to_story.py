"""
Priceless PAW Instagram ストーリーズ自動投稿スクリプト

仕組み：
1. リポジトリ直下の「インスタ-投稿フォルダ」から、今日の日付(YYYY-MM-DD)で始まるフォルダを探す
2. 見つからなければ何もせず終了（スキップ）
3. フォルダ内の画像のうち、ファイル名昇順で最初の1枚のみを使う
   （ストーリーズはフィードのカルーセルと異なり画像1枚のみ対応のため）
4. 画像をGitHubのRaw URL経由でInstagramに渡し、ストーリーズとして投稿する

必要な環境変数（GitHub Actions の Secrets から渡される。post_to_instagram.pyと共通）:
- IG_ACCESS_TOKEN         : Instagram Graph API アクセストークン
- IG_BUSINESS_ACCOUNT_ID  : InstagramビジネスアカウントID
- GITHUB_REPOSITORY       : "owner/repo" 形式（GitHub Actionsが自動で渡す）

★重要な既知の制約（2026-09-04時点でMeta公式ドキュメント・複数の第三者情報源で確認済み）：
Instagram Graph APIは、ストーリーズへの「リンク」スタンプの付与をサポートしていない。
画像そのものの自動投稿はできるが、リンクスタンプ（product_url.txtのURLを貼る操作）は
API経由では実行不可能なため、本スクリプトの投稿後、運用者が毎日手動でInstagramアプリを開き、
投稿されたストーリーズにリンクスタンプを追加する作業が必要（自動化不可）。

本スクリプトはpost_to_instagram.pyと独立して実行される想定（daily_post.yml側でcontinue-on-error）。
フィード投稿とストーリーズ投稿は別々のInstagramメディアであり、どちらかの成否がもう一方に影響しない。
ストーリーズ投稿の成否は「■済」への移動判定には使わない
（移動判定は引き続きフィード投稿=post_to_instagram.pyの成否のみを基準とする）。
"""

import sys
import time
import requests
import os

from common import (
    find_today_folder,
    load_images,
    build_raw_url,
    log,
    get_today_str,
)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def create_story_container(image_url: str, access_token: str) -> str:
    """ストーリーズ用のメディアコンテナを作成し、コンテナIDを返す"""
    ig_user_id = os.environ["IG_BUSINESS_ACCOUNT_ID"]
    url = f"{GRAPH_API_BASE}/{ig_user_id}/media"
    payload = {
        "image_url": image_url,
        "media_type": "STORIES",
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
        log(f"今日({get_today_str()})の投稿対象フォルダが見つかりません。ストーリーズ投稿をスキップします。")
        return 0

    log(f"ストーリーズ投稿対象フォルダを発見: {folder.name}")

    images = load_images(folder)
    if not images:
        log(f"エラー: {folder} に画像ファイルが見つかりません。ストーリーズ投稿を中止します。")
        return 1

    first_image = images[0]
    log(f"ストーリーズには最初の画像のみ使用します: {first_image.name}")

    try:
        image_url = build_raw_url(first_image)
        log(f"画像URL: {image_url}")

        creation_id = create_story_container(image_url, access_token)
        log(f"ストーリーズ用メディアコンテナ作成完了: creation_id={creation_id}")

        # コンテナがInstagram側で処理されるまで少し待つ
        time.sleep(5)

        result = publish_container(creation_id, access_token)
        log(f"ストーリーズ投稿完了！ post_id={result.get('id')}")
        log("★リンクスタンプはAPI非対応のため未設定です。運用者が手動でリンクスタンプを追加してください。")

    except requests.HTTPError as e:
        log(f"ストーリーズ投稿でAPIエラーが発生しました: {e}")
        if e.response is not None:
            log(f"レスポンス内容: {e.response.text}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
