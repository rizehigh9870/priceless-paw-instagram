# Priceless PAW Instagram 自動投稿

@priceless_paw への投稿を自動化するリポジトリです。

## 運用ルール（要点）

1. `YYYY-MM-DD_商品名` フォルダを作り、画像と `product_url.txt` を入れる（`caption.txt` は任意）
2. GitHubにプッシュすると、毎日 JST 5:47頃に GitHub Actions が自動でその日のフォルダを投稿する
   - ※GitHub Actionsのスケジュールは混雑状況により数時間遅延することがある（公式仕様）
3. 投稿が成功すると、フォルダは自動で `■済/YYYY-MM/` に月ごとに整理されて移動される
4. 当日フォルダが無い日は何もせずスキップされる（エラーにならない）
5. キャプションは**500文字以内**に収める（Threadsへのクロスポスト上限に合わせるため）
6. Instagram投稿とは別に、Threads APIでもThreadsへ投稿する（後述。Threads用Secrets未設定の場合はスキップされる）
7. フィード投稿とは別に、Instagramストーリーズにも自動で画像投稿する（後述。**リンクスタンプは運用者が毎日手動で追加する必要あり**）

詳細な仕様は [../インスタ自動投稿_仕様書.md](../インスタ自動投稿_仕様書.md) を参照してください。

## 初回セットアップ（GitHub側で1度だけ行う設定）

リポジトリの Settings → Secrets and variables → Actions で、以下を登録してください：

- `IG_ACCESS_TOKEN` : Instagram Graph API アクセストークン
- `IG_BUSINESS_ACCOUNT_ID` : InstagramビジネスアカウントID
- `THREADS_ACCESS_TOKEN` : Threads API アクセストークン（任意。未登録の場合はThreads投稿のみスキップされ、Instagram投稿は通常通り動作する）
- `THREADS_USER_ID` : Threads ユーザーID（任意。上記と同様）

※ アクセストークンは60日ごとに失効するため、期限が近づいたら再発行してSecretsを更新する必要があります。

### なぜThreads投稿が別処理として必要なのか

Instagramアプリ/Web管理画面から手動で投稿した場合、「シェア先」設定がONならThreadsへ自動でクロスポストされます。しかし、これはInstagramアプリ側のUI機能であり、Graph API経由の投稿（本リポジトリの自動投稿スクリプト）はこのクロスポスト機能の対象外です。そのため、Threadsにも投稿したい場合はThreads API（`graph.threads.net`）で別途明示的に投稿する必要があります。

### ストーリーズ投稿とリンクスタンプについて（重要な制約）

フィード投稿だけでは「投稿を見た人が実際に商品ページへワンタップで飛べない」導線上の課題があったため、当日の商品画像をInstagramストーリーズにも自動投稿するようにしています（`post_to_story.py`、フォルダ内の最初の画像1枚のみ使用。ストーリーズはフィードと異なりカルーセル非対応のため）。

**ただし、Instagram Graph APIはストーリーズへの「リンク」スタンプの付与をサポートしていません**（Meta公式ドキュメントで確認済み、2026-09時点）。画像そのものの自動投稿はできますが、そこにリンクを貼る操作だけはAPIでは実行できないため、**運用者が毎日、投稿されたストーリーズを開いてリンクスタンプを手動で追加する必要があります**（当日フォルダの`product_url.txt`のURLを貼る）。この手作業は申し送りログ（`log/YYYY-MM.md`）の「次に必要なこと」欄にも毎回自動で記載されます。

### スクリプト構成

```
scripts/
├─ common.py                 ← 共通処理（today判定、フォルダ探索、画像読み込み、Raw URL生成、ログ）
├─ post_to_instagram.py      ← Instagramフィードへの投稿のみを担当
├─ post_to_threads.py        ← Threadsへの投稿のみを担当（Secrets未設定なら何もせずスキップ）
├─ post_to_story.py          ← Instagramストーリーズへの画像投稿のみを担当（リンクスタンプは手動）
└─ move_completed_folder.py  ← 投稿完了フォルダを ■済/YYYY-MM/ へ移動
```

`daily_post.yml` は次の順序で実行します：

1. `post_to_instagram.py` を実行（失敗してもワークフローはここでは止めない）
2. `post_to_threads.py` を実行（失敗してもInstagram側の結果には影響させない）
3. `post_to_story.py` を実行（失敗してもフィード投稿・Threads投稿の結果には影響させない）
4. Instagram投稿（フィード）が成功していた場合のみ `move_completed_folder.py` でフォルダを移動
5. Instagram投稿（フィード）が失敗していた場合はここでジョブを失敗扱いにする（Actions上で気づけるように）

## 手動でテスト投稿したい場合

GitHubリポジトリの「Actions」タブ →「Instagram 自動投稿」→「Run workflow」で、スケジュールを待たずに即座に実行できます。
