"""
Priceless PAW 申し送りログ書き込みスクリプト（AIカンパニー構想 /log 運用）

post_to_instagram.py / post_to_threads.py / move_completed_folder.py の実行後、
daily_post.yml の最後に必ず呼び出す。

今日の投稿対象フォルダの有無・Instagram/Threadsそれぞれの成否を1つのログエントリに
まとめて /log/YYYY-MM.md に追記する。

AIカンパニー構想の完了条件「ログ追記が終わるまでタスク完了とみなさない」に従い、
ログ追記に失敗した場合はタスク未完了とみなしてジョブを失敗させる（exit 1）。
投稿自体が成功していてもログが残らなければ申し送りが途切れるため、
必ず気づけるようにする。

必要な環境変数（GitHub Actions の steps.<id>.outcome / steps.<id>.outputs から渡す）:
- IG_OUTCOME      : "success" / "failure" / "skipped" のいずれか
- THREADS_OUTCOME : "success" / "failure" / "skipped" のいずれか
- POSTED_FOLDER   : move_completed_folder.py が移動したフォルダ名（未設定なら空文字）
"""

import os
import sys

from common import find_today_folder, append_daily_log, log

OUTCOME_LABEL = {
    "success": "成功",
    "failure": "失敗",
    "skipped": "未実施",
}


def describe(name: str, outcome: str | None) -> str:
    label = OUTCOME_LABEL.get(outcome or "skipped", outcome or "未実施")
    return f"{name}{label}"


def main() -> int:
    # move_completed_folder.py が成功していればこの時点で既に ■済 へ移動済みのため、
    # 「今日のフォルダ」を再探索しても見つからないのが正常系。移動前のフォルダ名は
    # move_completed_folder.py が $GITHUB_OUTPUT 経由で渡してくれるので、まずそれを使う。
    posted_folder = os.environ.get("POSTED_FOLDER", "").strip()
    if posted_folder:
        folder_label = posted_folder
    else:
        # POSTED_FOLDER が無い場合（移動が行われなかった等）は、念のため今日のフォルダを
        # 直接探してみる。それでも見つからなければ本当に対象が無かったとみなす。
        folder = find_today_folder()
        folder_label = folder.name if folder else "（対象フォルダなし。移動済み、または当日投稿予定なし）"

    ig_outcome = os.environ.get("IG_OUTCOME")
    threads_outcome = os.environ.get("THREADS_OUTCOME")

    result = ", ".join([
        describe("Instagram投稿", ig_outcome),
        describe("Threads投稿", threads_outcome),
    ])

    if ig_outcome == "failure":
        next_action = "Instagram投稿の失敗原因を確認する"
    elif threads_outcome == "failure":
        next_action = "Threads投稿の失敗原因を確認する"
    else:
        next_action = "なし"

    try:
        append_daily_log(
            content=folder_label,
            result=result,
            next_action=next_action,
        )
    except Exception as e:
        # 「ログ追記が終わるまでタスク完了とみなさない」ため、
        # ログ書き込みの失敗はジョブ失敗として扱う。
        log(f"エラー: 申し送りログの書き込みに失敗しました: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
