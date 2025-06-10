#!/usr/bin/env python3

import http.server
import socketserver
import json
import subprocess
import os
import re
import uuid
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration from environment variables
PORT = int(os.getenv('PORT', 8081))
HOST = os.getenv('HOST', '127.0.0.1')
MAX_MESSAGES_PER_SESSION = int(os.getenv('MAX_MESSAGES_PER_SESSION', 50))
CONTEXT_WINDOW_SIZE = int(os.getenv('CONTEXT_WINDOW_SIZE', 5))
MAX_SESSIONS = int(os.getenv('MAX_SESSIONS', 100))
CLAUDE_TIMEOUT = int(os.getenv('CLAUDE_TIMEOUT', 60))
CLAUDE_STREAM_TIMEOUT = int(os.getenv('CLAUDE_STREAM_TIMEOUT', 180))
CLAUDE_COMMAND_PREFIX = os.getenv('CLAUDE_COMMAND_PREFIX', 'claude')
ENABLE_DANGEROUS_PERMISSIONS = os.getenv('ENABLE_DANGEROUS_PERMISSIONS', 'true').lower() == 'true'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
ENABLE_DEBUG_LOGS = os.getenv('ENABLE_DEBUG_LOGS', 'true').lower() == 'true'
LOG_FILE_PATH = os.getenv('LOG_FILE_PATH', 'logs/claude_chat.log')
CORS_ALLOW_ORIGIN = os.getenv('CORS_ALLOW_ORIGIN', '*')
ENABLE_CORS = os.getenv('ENABLE_CORS', 'true').lower() == 'true'

# 会話セッションを保持
chat_sessions = {}

class ClaudeChatHandler(http.server.SimpleHTTPRequestHandler):
    
    def do_GET(self):
        # favicon.icoのリクエストを処理
        if self.path == '/favicon.ico':
            self.send_response(204)  # No Content
            self.end_headers()
            return
        # 通常のGETリクエストを処理
        super().do_GET()
    
    def do_POST(self):
        if self.path == '/api/chat':
            self.handle_chat()
        elif self.path == '/api/chat/stream':
            # ストリーミングAPIを実装
            self.handle_chat_stream()
        else:
            self.send_error(404, "Not Found")
    
    def handle_chat(self):
        try:
            # Read request body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            user_message = data.get('message', '')
            session_id = data.get('session_id', str(uuid.uuid4()))
            
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] User ({session_id[:8]}): {user_message}")
            
            # セッション履歴を取得または初期化
            if session_id not in chat_sessions:
                chat_sessions[session_id] = []
                print(f"[INFO] 新しいセッション作成: {session_id[:8]}")
            
            history = chat_sessions[session_id]
            
            # ユーザーメッセージを履歴に追加
            history.append(f"User: {user_message}")
            
            # コンテキストを構築（設定値に基づく）
            context = "\n".join(history[-CONTEXT_WINDOW_SIZE:])
            
            # Claude Code CLIに送信
            response = self.handle_claude_conversation(user_message, context)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Assistant: {response[:100]}...")
            
            # 応答を履歴に追加
            history.append(f"Assistant: {response}")
            
            # セッションを保存（設定値に基づく）
            chat_sessions[session_id] = history[-MAX_MESSAGES_PER_SESSION:]
            
            # レスポンスを送信
            result = {
                "response": response,
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', CORS_ALLOW_ORIGIN)
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            import traceback
            error_msg = f"サーバーエラー: {str(e)}"
            print(f"[ERROR] {error_msg}")
            print(traceback.format_exc())
            
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', CORS_ALLOW_ORIGIN)
            self.end_headers()
            self.wfile.write(json.dumps({"error": error_msg}, ensure_ascii=False).encode('utf-8'))
    
    def handle_chat_stream(self):
        """ストリーミング対応のチャットハンドラ"""
        try:
            # Read request body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            user_message = data.get('message', '')
            session_id = data.get('session_id', str(uuid.uuid4()))
            
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Stream User ({session_id[:8]}): {user_message}")
            
            # セッション履歴を取得または初期化
            if session_id not in chat_sessions:
                chat_sessions[session_id] = []
                print(f"[INFO] 新しいセッション作成: {session_id[:8]}")
            
            history = chat_sessions[session_id]
            
            # ユーザーメッセージを履歴に追加
            history.append(f"User: {user_message}")
            
            # ストリーミングレスポンスのヘッダー設定
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.send_header('Connection', 'close')  # 接続を確実に閉じる
            self.send_header('Access-Control-Allow-Origin', CORS_ALLOW_ORIGIN)
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            
            # 即座にフラッシュ
            self.wfile.flush()
            
            # ストリーミング実行
            final_response = self.handle_claude_stream(user_message, session_id)
            
            # 応答を履歴に追加
            history.append(f"Assistant: {final_response}")
            
            # セッションを保存（設定値に基づく）
            chat_sessions[session_id] = history[-MAX_MESSAGES_PER_SESSION:]
            
            # 終了シグナル
            self.wfile.write(b'data: [DONE]\n\n')
            self.wfile.flush()
            
            print(f"[DEBUG] ストリーミング完了: {session_id[:8]}")
            
        except BrokenPipeError:
            print(f"[INFO] クライアント接続切断: {session_id[:8] if 'session_id' in locals() else 'unknown'}")
        except Exception as e:
            import traceback
            error_msg = f"ストリーミングエラー: {str(e)}"
            print(f"[ERROR] {error_msg}")
            print(traceback.format_exc())
            
            try:
                error_data = json.dumps({"error": error_msg}, ensure_ascii=False)
                self.wfile.write(f'data: {error_data}\n\n'.encode('utf-8'))
                self.wfile.write(b'data: [DONE]\n\n')
                self.wfile.flush()
            except:
                pass
    
    def handle_claude_stream(self, message, session_id):
        """Claude Code CLIをストリーミング実行"""
        try:
            # セッション履歴を取得してコンテキストを構築
            history = chat_sessions.get(session_id, [])
            
            # 最新の会話コンテキスト（設定値に基づく）を取得
            context_size = CONTEXT_WINDOW_SIZE * 2  # User + Assistant pairs
            recent_context = history[-context_size:] if len(history) > context_size else history[:]
            
            # コンテキストを文字列として構築
            context_str = ""
            if recent_context:
                context_str = "\n\n前の会話の履歴:\n" + "\n".join(recent_context[-6:-1])  # 現在のメッセージ以外
            
            # .mdファイルかどうかをチェック
            is_markdown_request = self.is_markdown_related_request(message)
            
            if is_markdown_request:
                claude_prompt = f"""{context_str}

{message}

重要な指示:
- 前の会話の文脈を理解して適切に応答してください
- ファイルの内容を読む場合は、必ず実際のコンテンツを表示してください
- .mdファイルの場合は、Markdown記法を使って見やすく表示してください
- コードブロックやその他のMarkdown要素を適切に使用してください
- 日本語で応答してください"""
            else:
                claude_prompt = f"""{context_str}

{message}

重要な指示:
- 前の会話の文脈を理解して適切に応答してください
- ユーザーが前回の選択肢に対して回答している場合は、その選択に応じて適切に実行してください
- ファイルの内容を読む場合は、必ず実際のソースコードを表示してください
- 要約や説明ではなく、実際のコードを見せてください
- コードブロックを使用して、適切にフォーマットしてください
- 日本語で応答してください"""
            
            print(f"[DEBUG] ストリーミング開始...")
            
            # Claude Code CLIをストリーミングモードで実行
            cmd = [CLAUDE_COMMAND_PREFIX, '-p']
            if ENABLE_DANGEROUS_PERMISSIONS:
                cmd.append('--dangerously-skip-permissions')
            cmd.extend(['--output-format', 'stream-json', '--verbose'])
            
            # 初期状態を送信
            init_data = {
                "type": "init",
                "message": "処理を開始しています...",
                "session_id": session_id
            }
            self.send_stream_data(init_data)
            
            # プロセス実行
            process = subprocess.Popen(
                cmd + [claude_prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,  # 無バッファ
                universal_newlines=True
            )
            
            full_response = ""
            current_message = ""
            
            # タイムアウト設定
            import signal
            def timeout_handler(signum, frame):
                raise TimeoutError("Claude Code プロセスがタイムアウトしました")
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(CLAUDE_STREAM_TIMEOUT)  # 設定値に基づくタイムアウト
            
            try:
                # ストリーミング処理
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                        
                    if output.strip():
                        try:
                            # JSONライン解析
                            line_data = json.loads(output.strip())
                            processed_data = self.process_stream_line(line_data, session_id)
                            
                            if processed_data:
                                self.send_stream_data(processed_data)
                                
                                # メッセージ内容を蓄積
                                if processed_data.get("type") == "assistant" and "content" in processed_data:
                                    current_message = processed_data["content"]
                                    
                        except json.JSONDecodeError as e:
                            print(f"[DEBUG] JSON解析エラー: {e} - Line: {output.strip()}")
                            continue
                            
                # プロセス終了待ち
                return_code = process.wait(timeout=10)
                
            except TimeoutError:
                print(f"[ERROR] Claude Code プロセスタイムアウト")
                process.kill()
                return "⏰ Claude Codeの処理がタイムアウトしました"
            finally:
                signal.alarm(0)  # タイムアウト解除
            
            if return_code == 0:
                if current_message:
                    full_response = current_message
                else:
                    full_response = "処理が完了しました。"
            else:
                stderr_output = process.stderr.read()
                print(f"[ERROR] Claude Code エラー (code: {return_code}): {stderr_output}")
                full_response = f"⚠️ Claude Code エラー:\n{stderr_output}"
                
            return full_response
            
        except Exception as e:
            import traceback
            print(f"[ERROR] ストリーミング実行エラー: {str(e)}")
            print(traceback.format_exc())
            return f"❌ ストリーミング実行エラー: {str(e)}"
    
    def process_stream_line(self, line_data, session_id):
        """ストリームラインデータを処理"""
        line_type = line_data.get("type", "")
        
        if line_type == "system":
            subtype = line_data.get("subtype", "")
            if subtype == "init":
                return {
                    "type": "system",
                    "message": "Claude Code初期化中...",
                    "session_id": session_id,
                    "details": line_data
                }
        elif line_type == "assistant":
            message = line_data.get("message", {})
            content_list = message.get("content", [])
            
            # テキストコンテンツを抽出
            text_content = ""
            for content in content_list:
                if content.get("type") == "text":
                    text_content += content.get("text", "")
            
            if text_content:
                return {
                    "type": "assistant",
                    "content": text_content,
                    "session_id": session_id,
                    "usage": line_data.get("usage", {})
                }
        elif line_type == "result":
            subtype = line_data.get("subtype", "")
            if subtype == "success":
                return {
                    "type": "result",
                    "message": "処理完了",
                    "content": line_data.get("result", ""),
                    "session_id": session_id,
                    "cost": line_data.get("cost_usd", 0),
                    "duration": line_data.get("duration_ms", 0)
                }
        
        return None
    
    def send_stream_data(self, data):
        """ストリームデータを送信"""
        try:
            json_data = json.dumps(data, ensure_ascii=False)
            self.wfile.write(f'data: {json_data}\n\n'.encode('utf-8'))
            self.wfile.flush()
        except Exception as e:
            print(f"[ERROR] ストリーム送信エラー: {e}")
    
    def handle_claude_conversation(self, message, context):
        """Claude Code CLIとの実際の対話"""
        try:
            # .mdファイルかどうかをチェック
            is_markdown_request = self.is_markdown_related_request(message)
            
            if is_markdown_request:
                # .mdファイル関連の場合はMarkdown記法を使用
                claude_prompt = f"""{context}

{message}

重要な指示:
- 前の会話の文脈を理解して適切に応答してください
- ファイルの内容を読む場合は、必ず実際のコンテンツを表示してください
- .mdファイルの場合は、Markdown記法を使って見やすく表示してください
- コードブロックやその他のMarkdown要素を適切に使用してください
- 日本語で応答してください"""
            else:
                # 通常のファイルの場合は従来通り
                claude_prompt = f"""{context}

{message}

重要な指示:
- 前の会話の文脈を理解して適切に応答してください
- ユーザーが前回の選択肢に対して回答している場合は、その選択に応じて適切に実行してください
- ファイルの内容を読む場合は、必ず実際のソースコードを表示してください
- 要約や説明ではなく、実際のコードを見せてください
- コードブロックを使用して、適切にフォーマットしてください
- 日本語で応答してください"""
            
            print(f"[DEBUG] Claude Codeに送信中...")
            
            # Claude Code CLIに送信
            cmd = [CLAUDE_COMMAND_PREFIX, '--print']
            if ENABLE_DANGEROUS_PERMISSIONS:
                cmd.append('--dangerously-skip-permissions')
            
            # デバッグ: コマンドを表示
            print(f"[DEBUG] コマンド: {' '.join(cmd)} '{claude_prompt[:50]}...'")
            
            result = subprocess.run(
                cmd + [claude_prompt],
                capture_output=True,
                text=True,
                timeout=CLAUDE_TIMEOUT  # 設定値に基づくタイムアウト
            )
            
            print(f"[DEBUG] 戻りコード: {result.returncode}")
            print(f"[DEBUG] stdout長: {len(result.stdout) if result.stdout else 0}")
            print(f"[DEBUG] stderr長: {len(result.stderr) if result.stderr else 0}")
            
            if result.returncode == 0 and result.stdout:
                response = result.stdout.strip()
                return response
            elif result.stderr:
                # エラーメッセージを詳しく表示
                error_detail = result.stderr.strip()
                print(f"[ERROR] Claude Code stderr: {error_detail}")
                return f"⚠️ Claude Code エラー:\n{error_detail}"
            else:
                return "Claude Codeからの応答がありませんでした。"
                
        except subprocess.TimeoutExpired:
            print("[ERROR] Claude Code タイムアウト")
            return "⏰ Claude Codeのレスポンスがタイムアウトしました（60秒）"
        except FileNotFoundError:
            print("[ERROR] Claude Code CLIが見つかりません")
            return "❌ エラー: Claude Code CLIが見つかりません。'claude'コマンドがPATHに含まれているか確認してください。"
        except Exception as e:
            import traceback
            print(f"[ERROR] Claude Code実行エラー: {str(e)}")
            print(traceback.format_exc())
            return f"❌ Claude Code実行エラー: {str(e)}"
    
    def is_markdown_related_request(self, message):
        """メッセージが.mdファイル関連かどうかをチェック"""
        import re
        
        # .mdファイルに関連するパターンをチェック
        md_patterns = [
            r'\.md\b',  # .md拡張子の直接言及
            r'README',  # READMEファイル
            r'REQUIREMENTS',  # REQUIREMENTSファイル
            r'CHANGELOG',  # CHANGELOGファイル
            r'マークダウン',  # マークダウン関連の日本語
            r'markdown',  # markdownの英語
        ]
        
        message_lower = message.lower()
        for pattern in md_patterns:
            if re.search(pattern, message_lower, re.IGNORECASE):
                return True
        
        return False
    
    def do_OPTIONS(self):
        # Handle CORS preflight
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', CORS_ALLOW_ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        """アクセスログをカスタマイズ"""
        # favicon.icoの404エラーを無視
        if len(args) > 0 and 'favicon.ico' in str(args):
            return
        # POSTリクエストのログは別途出力するので重複を避ける
        if len(args) > 0 and isinstance(args[0], str) and args[0].startswith('POST'):
            return
        super().log_message(format, *args)

if __name__ == "__main__":
    
    print("=" * 60)
    print(f"🚀 Claude Chat Server (安定版) ")
    print(f"📍 URL: http://{HOST}:{PORT}")
    print("=" * 60)
    print("💬 会話型インターフェース")
    print("🔧 デバッグモード有効")
    print(f"⏰ タイムアウト: {CLAUDE_TIMEOUT}秒")
    print("=" * 60)
    print("\n待機中...\n")
    
    # ポートの再利用を許可
    socketserver.TCPServer.allow_reuse_address = True
    
    try:
        with socketserver.TCPServer((HOST, PORT), ClaudeChatHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 サーバーを停止します...")
    except Exception as e:
        print(f"\n❌ サーバーエラー: {e}")
        import traceback
        traceback.print_exc()