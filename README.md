# Priceless PAW Instagram 自動投稿

@priceless_paw への投稿を自動化するリポジトリです。

## 運用ルール（要点）

1. `YYYY-MM-DD_商品名` フォルダを作り、画像と `product_url.txt` を入れる（`caption.txt` は任意）
2. GitHubにプッシュすると、毎日 JST 9:00 に GitHub Actions が自動でその日のフォルダを投稿する
3. 投稿が成功すると、フォルダは自動で `■済/` に移動される
4. 当日フォルダが無い日は何もせずスキップされる（エラーにならない）

詳細な仕様は [../インスタ自動投稿_仕様書.md](../インスタ自動投稿_仕様書.md) を参照してください。

## 初回セットアップ（GitHub側で1度だけ行う設定）

リポジトリの Settings → Secrets and variables → Actions で、以下の2つを登録してください：

- `IG_ACCESS_TOKEN` : Instagram Graph API アクセストークン
- `IG_BUSINESS_ACCOUNT_ID` : InstagramビジネスアカウントID

※ アクセストークンは60日ごとに失効するため、期限が近づいたら再発行してSecretsを更新する必要があります。

## 手動でテスト投稿したい場合

GitHubリポジトリの「Actions」タブ →「Instagram 自動投稿」→「Run workflow」で、スケジュールを待たずに即座に実行できます。
