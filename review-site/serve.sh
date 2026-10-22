#!/usr/bin/env bash
# 视频评审台启停：./serve.sh start|stop|restart|status
cd "$(dirname "$0")"
export PATH="$HOME/.local/node/bin:$PATH"
PORT="${PORT:-3100}"
PIDFILE=data/server.pid
mkdir -p data
start() {
  if status >/dev/null; then echo "已在运行（PID $(cat $PIDFILE)）"; return; fi
  set -a; . ./.env.local; set +a
  NODE_OPTIONS="--max-old-space-size=256" nohup node_modules/.bin/next start -p "$PORT" -H 0.0.0.0 >> data/server.log 2>&1 &
  echo $! > "$PIDFILE"
  echo "已启动 PID $! 端口 $PORT"
}
stop() { [ -f "$PIDFILE" ] && kill "$(cat $PIDFILE)" 2>/dev/null; rm -f "$PIDFILE"; echo "已停止"; }
status() { [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE)" 2>/dev/null && echo "运行中 PID $(cat $PIDFILE)"; }
case "$1" in
  start) start ;; stop) stop ;; restart) stop; sleep 1; start ;; status) status || echo "未运行" ;;
  *) echo "用法：$0 start|stop|restart|status" ;;
esac
