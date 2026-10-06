# 外部レビュー（GPT）の指摘と対応（2026-10-07）

依頼文は `review_request.md`、対象は `stations_readings.csv`（1,354 駅）。指摘 15 件（すべて香港）。

| 駅 | 項目 | 指摘 | 対応 | 根拠 |
|---|---|---|---|---|
| 深水埗 | 粤拼 | bou6 → bou2 | **修正** | 粵典（words.hk）「sam1 seoi2 bou2」。確認済みの一覧（`overrides/verified_hongkong.csv`）も修正 |
| 跑馬地總站 | 粤拼 | dei6 → dei2 | **修正** | 粵典「跑馬地 paau2 maa5 dei2」 |
| 錦上路 | 粤拼 | soeng5 → soeng6 | **修正** | 英語版 Wikipedia「Kam Sheung Road station」の Jyutping「gam2 soeng6 lou6」 |
| 藍地 | 粤拼 | dei6 → dei2 | 直さない | 粵典に項目なし。英語版 Wikipedia「Lam Tei」は「laam4 dei6」 |
| 鳳地 | 粤拼 | dei6 → dei2 | 直さない | 粵典・Wikipedia とも確かな出典なし（地名の「地」の変調はあり得るが未確認） |
| 大興(南)・大興(北)・山景(南)・山景(北)・上環(西港城)總站 | 粤拼・広東語カナ（10 件） | 粤拼・カナに漢字がそのまま入っている | **修正（不具合）** | 括弧付きの名前を粤拼の変換ライブラリが読めなかった。括弧の中と外を別々に読むよう `tools/textconv.py` を修正（ピンインも「Dàxīng (Nán)」の形に整えた） |

修正後: 大興(南) daai6 hing1 (naam4)・タイヒン(ナム)、上環(西港城)總站 soeng6 waan4 (sai1 gong2 sing4) zung2 zaam6・ションワン(サイコンシン)・チョンチャム。
上海・広州・深圳・高鉄の駅には指摘なし。
