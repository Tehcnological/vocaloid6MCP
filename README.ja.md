# VOCALOID6 MCP

[English README](README.md)

MCP クライアント（Claude、Cursor、VS Code、Codex、Gemini CLI など）の AI アシスタントから Windows の **VOCALOID6 Editor** を操作し、**VOCALOID3・4・5・6** 用の
プロジェクトを作成できるようにします。英語・日本語・中国語・韓国語・スペイン語のメロディと歌詞、インストール済みの
すべての音源（VOCALOID:AI 音源と VOCALOID3/4/5 音源）、ピッチや表情のカーブ、再生、WAV/MIDI 書き出しに対応します。

| 部分 | 内容 |
|---|---|
| プロジェクト系ツール（`.vpr`） | VOCALOID5/6 のプロジェクトを直接読み書きします。編集ツールは任意の `path` を取り、指定するとそのファイルを編集（VOCALOID6 は閉じたままで可）、省略すると VOCALOID6 で開いているプロジェクトをライブ編集します。 |
| ライブツール（UI オートメーション） | Windows のアクセシビリティ API で、起動中のエディターの開く・保存・再読み込み・再生・停止・WAV/MIDI 書き出し・MIDI 読み込みを行います。 |
| `export_vsqx` | VOCALOID3（vsq3）・VOCALOID4（vsq4）エディター用の `.vsqx` を書き出します。Yamaha 同梱のスキーマで検証済み。 |

## 仕組み（プラグインがない理由）

VOCALOID6 にはプラグインの仕組みがなく、ライセンスでリバースエンジニアリングが禁止されているため、本ツールは VOCALOID6 の
コードに一切触れません。

- `.vpr` 形式は VOCALOID6 自身が保存したプロジェクトから調べました。`.vsqx` はエディターのフォルダにある
  `vsq3.xsd` / `vsq4.xsd` に従います。
- ライブツールはスクリーンリーダーと同じ **Windows UI オートメーション** で VOCALOID6 のメニューとダイアログを操作します。
  キー入力は送らないので、他のウィンドウに文字が入ることはありません。
- **ライブ編集**は、VOCALOID6 でプロジェクトを保存（手作業の変更も保持）→ `.vpr` を編集 →「ファイル > 元に戻す（Revert）」で
  再読み込み、の順に行います。1回の呼び出しが本サーバーの `undo` / `redo` の1単位です（再読み込み後は VOCALOID6 自身の
  取り消し履歴はリセットされます）。1回に数秒かかります。
- **発音は VOCALOID6 自身が決めます。** 新しい音符には仮の発音記号を入れ、VOCALOID6 が読み込み時に歌詞から正しい発音を
  付けます。発音を変えたいときだけ `phoneme` を指定してください（その音符は保護されます）。

ライブツールが使う要素はすべて `src/vocaloid6_mcp/ui.py` の `SELECTORS` 表にあり、VOCALOID6 の更新後は `self_check` で
一致しなくなった要素を確認できます。プロジェクト系ツールは UI に依存しません。

## 必要なもの

- VOCALOID6 Editor が入った Windows（6.13 で確認。既定のインストール先 `C:\Program Files\VOCALOID6\Editor`）
- 音源：VOCALOID6 の AI 音源と、VOCALOID6 が読み込める VOCALOID3/4/5 音源。VOCALOID2 には対応していません。
- ローカル（stdio）サーバーを起動できる MCP クライアント：Claude Desktop、Claude Code、Cursor、VS Code、Windsurf、
  Cline、Continue、Codex CLI、Gemini CLI、LM Studio など。

## インストール

次のどれか1つを選びます。どれも、MCP クライアントに「起動するコマンド」を渡すだけです。

**A. 1ファイル版（Python 不要）。** このリポジトリの **Releases** ページから `vocaloid6-mcp.exe` をダウンロードし、
好きなフォルダー（例 `C:\Tools\`）に置きます。コマンドはそのファイルのパス `C:\Tools\vocaloid6-mcp.exe` です。

- ダウンロードが壊れていないかの確認（任意）：PowerShell で `Get-FileHash C:\Tools\vocaloid6-mcp.exe` を実行し、
  リリースの `SHA256SUMS.txt` と同じ値になることを確かめます。
- exe にはコード署名がありません。Windows にブロックされたら、ファイルを右クリック、プロパティ、
  **許可する** にチェックして OK。
- 漢字をかなに変換する機能（`pykakasi`）が入っています。

**B. uvx（常に最新のコード）。** [uv](https://docs.astral.sh/uv/) が必要です。クローン不要で、クライアントが初めて
起動したときに uv がサーバーをダウンロードしてキャッシュします。コマンドは `uvx`、引数は次のとおりです。

```text
--from "vocaloid6-mcp[kanji] @ git+https://github.com/Tehcnological/vocaloid6MCP" vocaloid6-mcp
```

**C. クローンから（コードを変更する場合）。** Python 3.11 以上と uv が必要です。

```bash
git clone https://github.com/Tehcnological/vocaloid6MCP vocaloid6-mcp
```

```bash
cd vocaloid6-mcp
uv venv -p 3.11
uv pip install -e ".[kanji]"
```

コマンドは `C:\path\to\vocaloid6-mcp\.venv\Scripts\vocaloid6-mcp.exe` になります。

### MCP クライアントへの登録

例は A の `C:\Tools\vocaloid6-mcp.exe` です。B の場合は、コマンドを `"command": "uvx"` にし、各クライアントの下に
書いた `args` を加えます。設定ファイルを編集したら、クライアントを再起動（または MCP サーバーを再読み込み）します。
JSON ではパスの `\` を `\\` と書きます。

**Claude Desktop・Cursor・Windsurf・Cline・Gemini CLI・LM Studio** は同じ JSON 形式です。

```json
{
  "mcpServers": {
    "vocaloid6": {
      "command": "C:\\Tools\\vocaloid6-mcp.exe",
      "args": []
    }
  }
}
```

B の場合：`"command": "uvx", "args": ["--from", "vocaloid6-mcp[kanji] @ git+https://github.com/Tehcnological/vocaloid6MCP", "vocaloid6-mcp"]`。

| クライアント | 設定ファイル（`mcpServers` に `vocaloid6` の項目を追加） |
|---|---|
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json`（設定、開発者、構成を編集）。Microsoft Store 版は `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json` を読むことがあります。 |
| Cursor | `%USERPROFILE%\.cursor\mcp.json`（全プロジェクト）または `.cursor\mcp.json`（1プロジェクト）。項目に `"type": "stdio"` を追加。 |
| Windsurf（現 Devin Desktop） | `%APPDATA%\devin\mcp_config.json`。古い Windsurf は `%USERPROFILE%\.codeium\windsurf\mcp_config.json` |
| Cline | Cline パネル、MCP Servers、Configure、**Configure MCP Servers** で `cline_mcp_settings.json` が開きます |
| Gemini CLI | `%USERPROFILE%\.gemini\settings.json`。1行で登録するなら `gemini mcp add -s user vocaloid6 "C:\Tools\vocaloid6-mcp.exe"` |
| LM Studio（0.3.17 以上） | `%USERPROFILE%\.lmstudio\mcp.json`（Program タブ、Install、Edit mcp.json） |

**Claude Code**（コマンド1行、ファイル編集なし）

```bash
claude mcp add --scope user vocaloid6 -- "C:\Tools\vocaloid6-mcp.exe"
```

```bash
claude mcp add --scope user vocaloid6 -- uvx --from "vocaloid6-mcp[kanji] @ git+https://github.com/Tehcnological/vocaloid6MCP" vocaloid6-mcp
```

**VS Code（GitHub Copilot のエージェントモード）**：コマンドパレットで **MCP: Open User Configuration**
（ワークスペース単位なら `.vscode\mcp.json`）。最上位のキーは `mcpServers` ではなく `servers` です。

```json
{
  "servers": {
    "vocaloid6": {
      "type": "stdio",
      "command": "C:\\Tools\\vocaloid6-mcp.exe"
    }
  }
}
```

Copilot の新しい共通ファイル `%USERPROFILE%\.copilot\mcp-config.json` とワークスペースの `.mcp.json` は、上の
`mcpServers` 形式を使います。

**Continue**（MCP はエージェントモードのみ）：ワークスペースに `.continue\mcpServers\vocaloid6.yaml` を作ります。

```yaml
name: VOCALOID6
version: 0.0.1
schema: v1
mcpServers:
  - name: vocaloid6
    type: stdio
    command: 'C:\Tools\vocaloid6-mcp.exe'
```

B の場合：`command: uvx` と `args: ["--from", "vocaloid6-mcp[kanji] @ git+https://github.com/Tehcnological/vocaloid6MCP", "vocaloid6-mcp"]`。

**Codex CLI**：`%USERPROFILE%\.codex\config.toml` に追加します（TOML では単一引用符で囲むと `\` をそのまま書けます）。

```toml
[mcp_servers.vocaloid6]
command = 'C:\Tools\vocaloid6-mcp.exe'
tool_timeout_sec = 300  # ライブ編集や WAV 書き出しは既定の 60 秒を超えることがあります
```

B の場合：`command = "uvx"` と `args = ["--from", "vocaloid6-mcp[kanji] @ git+https://github.com/Tehcnological/vocaloid6MCP", "vocaloid6-mcp"]`。
1行で登録するなら `codex mcp add vocaloid6 -- "C:\Tools\vocaloid6-mcp.exe"`（`tool_timeout_sec` は後から手で追加）。

任意の環境変数：`VOCALOID6_EXE`（`VOCALOID6.exe` のパス）。JSON では `"env": {"VOCALOID6_EXE":
"D:\\Apps\\VOCALOID6\\Editor\\VOCALOID6.exe"}`、TOML では `env = { VOCALOID6_EXE = 'D:\Apps\...' }` と書きます。

### どのクライアントでも使い方のルールを使う

サーバーは基本ルール（ティック、番号、歌詞、ライブ操作の注意）を MCP の instructions として送り、`usage_guide`
ツールは手順と品質ルールの全文（[skill/SKILL.md](skill/SKILL.md)）を返します。instructions をモデルに渡さない
クライアントもあるので、手順が飛ばされるときは「まず usage_guide を呼んで」と頼んでください。Claude では
`skill` フォルダーをスキルとして入れることもできます（例 `.claude/skills/vocaloid6/`）。スキルに対応しない
エージェントやクライアント向けの説明は [AGENTS.md](AGENTS.md) にあります。

ツールは 45 個あります。VS Code は1回のリクエストで 128 個まで、Cursor は以前は最初の 40 個しか送らなかったので、
ツールが多すぎると警告されたら使わないものをオフにします（VS Code：チャットのツール選択、Codex：`enabled_tools`、
Gemini CLI：`includeTools`）。

### 曲作り用スクリプト（任意）

スキルの `scripts/` は伴奏に合わせて歌うためのツールです：`analyze_backing.py`（テンポ、1拍目、キー、小節ごとの
コード、コード進行のループ）、`check8.py`（8小節のクリック＋音階チェック）、`assemble.py` と `mix.py`（ステムの配置と
ボーカルのミックス）。サーバーの一部ではなく、`librosa` と `soundfile` を入れた別の Python と、PATH 上の ffmpeg が
必要です。

```bash
python -m venv %LOCALAPPDATA%\song-analysisenv
```

```bash
%LOCALAPPDATA%\song-analysisenv\Scripts\pip install librosa soundfile
```

### 1ファイル版を自分でビルドする

```bash
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

uv が必要です。`dist\vocaloid6-mcp.exe`（PyInstaller、約 20 MB）、`SHA256SUMS.txt`、中に入ったパッケージの一覧を
作ります。`v0.4.0` のようなタグを push すると GitHub Actions が同じスクリプトを実行し、ファイルを下書きのリリースに
添付します。公開は手動です。

## 使い方

AI アシスタントにこう頼めます。

- 「VOCALOID6 の準備はできてる？」→ `vocaloid_status`
- 「AI 音源で 128 BPM の新しい曲を作って、A4 A4 B4 で さくら さくら と歌わせて」
- 「英語の音源のトラックを追加して、C4 から四分音符で 'hel-lo world' と歌わせて」
- 「デスクトップに WAV を書き出して」

基本：四分音符 = 480 ティック、音高 `C4` = 60、パート位置は絶対位置・音符位置はパート相対、トラック・パート・音符の番号は 0 から。

### 歌詞

| 言語 | 1音符あたり | 例 |
|---|---|---|
| 日本語 | 1モーラ（ー は母音を伸ばす `-` 音符） | `きゃりーぱみゅぱみゅ` → きゃ り - ぱ みゅ ぱ みゅ |
| 英語・スペイン語 | 1音節（VOCALOID 形式 `hel-` + `lo`） | `Hel-lo, beau-ti-ful world` → hel- lo beau- ti- ful world |
| 中国語 | 1字、またはピンイン1音節 | `我爱你` → 我 爱 你 |
| 韓国語 | 1音節 | `사랑해` → 사 랑 해 |

英語の注意：複数音節の単語を1音符に置くと（`hello`）`u:` になるのでハイフンで区切ってください（ツールが警告します）。
日本語以外の `-` 伸ばし音符も `u:` になるため、伸ばし音符には母音を `phoneme` として指定してください。

### 音源と世代

| 世代 | 音源 | トラック種別 | プロジェクト形式 |
|---|---|---|---|
| VOCALOID6 | VOCALOID:AI 音源（複数言語） | VOCALOID:AI | `.vpr` |
| VOCALOID5 | V5 音源 | VOCALOID | `.vpr`（ファイルバージョン 5.0.0 で書き出し） |
| VOCALOID4 / 3 | V4 / V3 音源 | VOCALOID | `.vpr`、または `export_vsqx` で `.vsqx` |

`list_voicebanks` はレジストリ（`HKLM\SOFTWARE\VOCALOID3..6`）を読みます。AI 音源は対応言語を返し、旧世代の音源の言語は
音源名から推定します（`language_source: "name"`）。

### ツール一覧

- **アプリ**：`vocaloid_status`、`launch_vocaloid`、`close_vocaloid`、`self_check`
- **プロジェクト**：`new_project`、`open_project`、`save_project`、`reload_project`、`get_project`、`undo`、`redo`
- **テンポ**：`set_tempo`、`remove_tempo`、`set_time_signature`
- **音源**：`list_voicebanks`、`get_voicebank`、`list_styles`
- **トラック・パート**：`add_track`、`edit_track`、`remove_track`、`add_part`、`edit_part`、`remove_part`、`fit_part`
- **音符・歌詞**：`list_notes`、`add_notes`、`edit_notes`（手動ビブラート、AI 音符の設定、タイミングツール `timing` = 各音素の開始と音の終わり、音符の先頭からのティック）、`delete_notes`、`assign_lyrics`、`add_melody`（例 `A4:1 A4:1 B4:2 r:1`）
- **カーブ**：`set_curve`、`get_curve`、`clear_curve`
- **再生・書き出し**：`play`、`stop`、`export_wav`（`tracks=[...]` でそのトラックだけのステムを書き出し、ミュート・ソロは後で元に戻ります。`bit_depth=24` でビット深度を指定）、
  `export_midi`、`import_midi`、`export_vsqx`
- **ユーティリティ**：`note_to_midi`、`midi_to_note`、`beats_to_ticks`、`ticks_to_beats`、`split_lyrics`

## 安全性

- `open_project`、`new_project(open_in_vocaloid=true)`、`close_vocaloid` は、`force=true` でない限り VOCALOID6 の未保存の
  変更を破棄しません。
- ライブ編集は先に開いているプロジェクトを保存し、ファイルのスナップショットを取ります（プロジェクトごとに直近 50 件、
  `%LOCALAPPDATA%\vocaloid6-mcp\history`）。`undo` で戻せます。
- `.vpr` は一時ファイル経由で書き込み、本サーバーが知らない zip の項目やフィールドもそのまま残します。

## テスト

```bash
uv pip install -e ".[kanji,test]"
.venv\Scripts\python tests\e2e_test.py          # ファイル・音源・VSQX・ユーティリティのツール（stdio 経由）
.venv\Scripts\python tests\e2e_test.py --live   # 起動中の VOCALOID6 も操作（音源が必要）
.venv\Scripts\python tests\schema_check.py      # 全ツールのスキーマを厳しいクライアントの規則で検査
```

`schema_check.py` はツール一覧を取得する普通の MCP クライアントで、各入力スキーマを Gemini・Codex・VS Code・Cursor の
最も厳しい規則で検査します（規則はファイル冒頭に記載）。`MCP_SERVER_EXE=dist\vocaloid6-mcp.exe` を設定すると `e2e_test.py` を
1ファイル版に対して実行します。`schema_check.py` には exe のパスを渡せます。

ライブテストは一時プロジェクトを `force=false` で開くため、VOCALOID6 に未保存の変更があると停止します。
`lxml` があれば VSQX を Yamaha の `vsq3.xsd` / `vsq4.xsd` で検証します。

## 制限

- ライブツールはメニューを開く間 VOCALOID6 のウィンドウを前面に出します。そのときの入力は VOCALOID6 に届き、ショートカットで
  開いたダイアログが次の操作を妨げることがあります（残った「開く」「保存」ダイアログとその「ファイルが見つかりません」は自動で閉じ、
  それ以外のダイアログは報告します）。ライブツールの実行中、特に
  `tests/e2e_test.py --live` の間はキーボードに触れないでください。
- ライブツールには VOCALOID6 のウィンドウが必要です。VOCALOID6 の更新でメニューが変わることがあります（`self_check` で確認）。
  `.vpr` のツールは影響を受けません。
- 確認したのは VOCALOID6 6.13 と VOCALOID4・VOCALOID6 AI 音源のみです。VOCALOID3・5 の音源も同じレジストリ走査で
  見つかりますが、手元になかったため未確認です。
- VOCALOID6 は VSQX のプリメジャーを無視するため、VOCALOID6 で開いた `.vsqx` は VOCALOID3/4 より1小節後ろから始まります。
- スタイルプリセットは一覧のみで、適用は VOCALOID6 で行います。

## ライセンス

MIT（[LICENSE](LICENSE) を参照）。Yamaha とは関係ありません。VOCALOID はヤマハ株式会社の商標です。

リリースの単体 `.exe` には GPL-3.0-or-later の pykakasi が含まれるため、`.exe` 全体は GPL-3.0-or-later で配布されます。各リリースに `EXE-LICENSE.md` と `GPL-3.0.txt` を添付しています。このリポジトリのソースコードは MIT のままです。
