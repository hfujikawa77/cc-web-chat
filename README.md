# Claude Code Web Chat

Chat-based Web UI for Claude Code CLI with smartphone control support.  
スマートフォンからClaude Code CLIを制御できるチャットベースのWebインターフェースです。

## Installation

### From PyPI (when published)
```bash
pip install claude-code-chat
```

### From Source
```bash
git clone <repository-url>
cd claude-code-chat
pip install -e .
```

## Usage

### Single Instance
```bash
# Full command name
claude-code-chat

# Short alias
ccc

# Custom port
claude-code-chat --port 8082

# Show help
claude-code-chat --help
```

### Multiple Instances
```bash
# Start multiple instances on different ports
claude-code-chat --port 8081 &    # Instance 1
claude-code-chat --port 8082 &    # Instance 2
claude-code-chat --port 8083 &    # Instance 3

# Access different projects simultaneously
cd /path/to/project1 && claude-code-chat --port 8081 &
cd /path/to/project2 && claude-code-chat --port 8082 &
```

**Features:**
- 🚀 **Multiple Projects**: Run separate instances for different projects
- 🔍 **Port Conflict Detection**: Automatic port availability checking
- 📱 **Instance Identification**: Each instance shows unique Process ID
- 📁 **Independent Working Directories**: Each instance uses its startup directory as root

## 📱 スマートフォンからの接続手順

**前提条件:**
- ✅ サーバーが起動していること
- ✅ PCとスマートフォンが同一WiFiネットワークに接続済み

### 1. WSL2のIPアドレス確認
**WSLターミナルで実行**
```bash
hostname -I
# 例: 172.20.240.2 ← この数字をメモ
```

### 2. WindowsのIPアドレス確認
**コマンドプロンプトで実行**
```cmd
ipconfig
# 例: 192.168.1.100 ← この数字をメモ
```

### 3. ポート転送設定
**コマンドプロンプト（管理者権限）で実行**  
Windowsキー → 「cmd」と入力 → 右クリック → 「管理者として実行」
```cmd
netsh interface portproxy add v4tov4 listenport=8081 listenaddress=0.0.0.0 connectport=8081 connectaddress=172.20.240.2
```
※ `connectaddress=` の部分は手順1で確認したWSL2のIPアドレスに変更してください

### 4. ファイアウォール設定
**同じコマンドプロンプト（管理者権限）で続けて実行**
```cmd
netsh advfirewall firewall add rule name="WSL2 Claude Chat" dir=in action=allow protocol=TCP localport=8081
```

### 5. スマートフォンブラウザでアクセス
```
http://[手順2でメモしたWindowsのIP]:8081/claude_chat.html

例: http://192.168.1.100:8081/claude_chat.html
```

### 🔧 うまくいかない場合
**コマンドプロンプト（管理者権限）で実行**
```cmd
# 転送設定確認
netsh interface portproxy show all

# ポート確認
netstat -an | findstr 8081

# 設定削除
netsh interface portproxy delete v4tov4 listenport=8081 listenaddress=0.0.0.0
```

## 概要

スマートフォンブラウザから Claude Code CLI を操作できる本格的なチャット型WebUIです。ストリーミング対応により、Claude Codeの実行状況をリアルタイムで確認できます。

## ✨ 主要機能

### 🚀 ストリーミング対応
- **リアルタイム進捗表示**: Claude Codeの実行状況をリアルタイムで表示
- **Server-Sent Events**: 双方向通信による即座な応答
- **進捗アイコン**: 🔄 初期化 → ⚙️ システム準備 → 💭 応答中 → ✅ 完了
- **コスト・時間表示**: 実行コストと処理時間の可視化
- **ESCキャンセル**: 処理中にESCキーで即座にキャンセル可能

### 📁 ディレクトリナビゲーション
- **セッション別作業ディレクトリ**: チャットセッションごとに独立した作業環境
- **GUI操作**: ディレクトリバーによる視覚的なパス表示と操作
- **ディレクトリコマンド**: `cd`, `ls`, `pwd` コマンドでの直接操作

### 💬 高度なチャットインターフェース
- **日本語サポート**: UTF-8エンコーディングによる完全な日本語表示
- **モダンUI**: レスポンシブデザインとリアルタイムタイピング表示
- **会話文脈保持**: 選択肢→回答の流れを理解した対話
- **Markdownレンダリング**: .mdファイル時の美しい表示
- **コードハイライト**: Prism.js による多言語シンタックスハイライト

### 🔧 Claude Code 統合
- **ストリーミング実行**: `--output-format stream-json` による進捗表示
- **権限バイパス**: ファイル作成権限を自動的に許可
- **作業ディレクトリ認識**: セッション別ディレクトリでの確実なファイル操作
- **文脈理解**: 会話履歴とディレクトリ情報を含む適切な応答
- **3分タイムアウト**: 長時間処理にも対応
- **フォールバック機能**: ストリーミング失敗時の通常モード切り替え

## 📁 ファイル操作
- **ファイル作成**: Claude Code CLIが指定ディレクトリに直接ファイルを作成
- **プログラミング支援**: Python、JavaScript等のファイル生成
- **テストファイル**: 自動テストファイル生成対応
- **ディレクトリ管理**: セッションごとの独立した作業環境
- **パス解決**: 相対パス・絶対パスの適切な処理

## Quick Start

```bash
# Install and start
pip install -e .
claude-code-chat

# Access via browser
# http://127.0.0.1:8081/claude_chat.html
```

## 🏗️ アーキテクチャ

```
[スマートフォンブラウザ] ←→ [HTML/JS UI] ←→ [Python HTTPサーバー] ←→ [Claude Code CLI]
                ↓                    ↓                    ↓                  ↓
          [ディレクトリバー]      [ストリーミング]      [セッション管理]      [cwd設定]
          [GUIナビゲーション]      [進捗表示]       [会話履歴]       [ディレクトリ管理]
          [ESCキャンセル]         [コスト表示]      [ディレクトリ情報]   [マルチインスタンス]
```

## 📋 ファイル構成

```
pyproject.toml          # パッケージ設定
requirements.txt        # Python依存パッケージ  
README.md              # このファイル
claude_code_chat/      # パッケージ本体
├── __init__.py
├── server.py          # HTTPサーバー
├── claude_chat.html   # チャットUI
└── CLAUDE.md          # Claude Code用プロジェクトガイド
```

## 💡 使用例

```bash
# ファイル作成
「test.py ファイルを作成して」
→ 🔄 処理開始 → ⚙️ 初期化 → 💭 応答中 → ✅ 完了

# ディレクトリ移動
cd ./subdir            # サブディレクトリへ移動
ls                     # ディレクトリ内容一覧
pwd                    # 現在のパス表示

# 会話の文脈理解
Claude: 「実行したいファイルを選んでください: 1. calculator.py 2. server.py」
User: 「1」
→ Claude が選択肢を理解して calculator.py を実行
```

## 🔧 主要技術

- **Server-Sent Events**: リアルタイムストリーミング
- **セッション管理**: UUID生成、履歴保持
- **フォールバック**: ストリーミング失敗時の自動切り替え
- **Markdown対応**: .mdファイル時の美しい表示とシンタックスハイライト
- **ESCキャンセル**: 処理中の即座なキャンセル

## ⚠️ 注意事項

- **ローカル開発専用**: 認証なし、localhost のみ
- **権限バイパス**: `--dangerously-skip-permissions` 使用
- **本番環境非対応**: セキュリティ機能なし
