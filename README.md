# Priceless PAW Instagram 自動投稿

@priceless_paw への投稿を自動化するリポジトリです。

## 運用ルール（要点）

1. `YYYY-MM-DD_商品名` フォルダを作り、画像と `product_url.txt` を入れる（`caption.txt` は任意）
2. GitHubにプッシュすると、毎日 JST 10:43頃に GitHub Actions が自動でその日のフォルダを投稿する
   - ※GitHub Actionsのスケジュールは混雑状況により数時間遅延することがある（公式仕様）
3. 投稿が成功すると、フォルダは自動で `■済/YYYY-MM/` に月ごとに整理されて移動される
4. 当日フォルダが無い日は何もせずスキップされる（エラーにならない）
5. キャプションは**500文字以内**に収める（Threadsへのクロスポスト上限に合わせるため）
6. Instagram投稿とは別に、Threads APIでもThreadsへ投稿する（後述。Threads用Secrets未設定の場合はスキップされる）

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

### スクリプト構成

```
scripts/
├─ common.py                 ← 共通処理（today判定、フォルダ探索、画像読み込み、Raw URL生成、ログ）
├─ post_to_instagram.py      ← Instagramへの投稿のみを担当
├─ post_to_threads.py        ← Threadsへの投稿のみを担当（Secrets未設定なら何もせずスキップ）
└─ move_completed_folder.py  ← 投稿完了フォルダを ■済/YYYY-MM/ へ移動
```

`daily_post.yml` は次の順序で実行します：

1. `post_to_instagram.py` を実行（失敗してもワークフローはここでは止めない）
2. `post_to_threads.py` を実行（失敗してもInstagram側の結果には影響させない）
3. Instagram投稿が成功していた場合のみ `move_completed_folder.py` でフォルダを移動
4. Instagram投稿が失敗していた場合はここでジョブを失敗扱いにする（Actions上で気づけるように）

## 手動でテスト投稿したい場合

GitHubリポジトリの「Actions」タブ →「Instagram 自動投稿」→「Run workflow」で、スケジュールを待たずに即座に実行できます。
