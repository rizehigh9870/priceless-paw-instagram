"""
Priceless PAW 投稿完了フォルダ移動スクリプト

post_to_instagram.py と post_to_threads.py の実行後に呼び出す。
今日の投稿対象フォルダを「■済/YYYY-MM/」配下へ移動する（月ごとに整理）。

Instagram投稿（post_to_instagram.py）が成功していることを前提に、
daily_post.yml 側で「Instagram投稿が成功した場合のみ」このスクリプトを実行する。
Threads投稿の成否は問わない（Threads未設定・失敗でもInstagram投稿が成功していれば移動する）。

今日のフォルダが見つからない場合は、その日は投稿対象外だったとみなしエラーにせず終了する。
"""

import sys

from common import find_today_folder, move_to_done, log, get_today_str


def main() -> int:
    folder = find_today_folder()
    if folder is None:
        log(f"今日({get_today_str()})の対象フォルダが見つかりません。移動をスキップします。")
        return 0

    move_to_done(folder)
    return 0


if __name__ == "__main__":
    sys.exit(main())
