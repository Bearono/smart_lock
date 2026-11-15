#!/usr/bin/env bash
# 性能测试一键运行脚本 (Linux / macOS / Git Bash)
#
# 用法:
#   cd BE_smart_lock/smart_lock
#   source .venv/bin/activate   # 或 . .venv/Scripts/activate
#   bash tests/perf/run_perf.sh
#   HOST_URL=http://192.168.1.10:8000 DURATION=3m bash tests/perf/run_perf.sh
#   LOGIN_ONLY=1 bash tests/perf/run_perf.sh    # 只压 /api/login
#
# 环境变量:
#   HOST_URL       (默认 http://localhost:8000)
#   DURATION       (默认 2m)
#   CONCURRENCIES  (默认 "10 50 100", 空格分隔)
#   SPAWN_RATE     (默认 20)
#   SKIP_PREPARE=1 跳过账号准备
#   LOGIN_ONLY=1   只跑 LoginOnlyUser

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
mkdir -p "$RESULTS_DIR"

HOST_URL="${HOST_URL:-http://localhost:8000}"
DURATION="${DURATION:-2m}"
CONCURRENCIES="${CONCURRENCIES:-10 50 100}"
SPAWN_RATE="${SPAWN_RATE:-20}"

if [ -z "$SKIP_PREPARE" ]; then
    echo "[perf] 准备测试账号 ..."
    python "$SCRIPT_DIR/prepare_data.py"
fi

USER_CLASS="SmartLockUser"
LABEL_SUFFIX=""
if [ -n "$LOGIN_ONLY" ]; then
    USER_CLASS="LoginOnlyUser"
    LABEL_SUFFIX="_login"
fi

for c in $CONCURRENCIES; do
    LABEL="c${c}${LABEL_SUFFIX}"
    CSV_PREFIX="$RESULTS_DIR/$LABEL"
    HTML_PATH="$RESULTS_DIR/${LABEL}.html"

    echo
    echo "==== 档位: 并发 $c, 时长 $DURATION ===="
    locust \
        -f "$SCRIPT_DIR/locustfile.py" \
        --headless \
        -u "$c" \
        -r "$SPAWN_RATE" \
        -t "$DURATION" \
        --host "$HOST_URL" \
        --csv "$CSV_PREFIX" \
        --html "$HTML_PATH" \
        --only-summary \
        $USER_CLASS || echo "[perf] locust 返回非零, 继续下一档"

    sleep 5
done

echo
echo "[perf] 全部档位执行完毕, 结果目录: $RESULTS_DIR"
echo "[perf] 下一步: python tests/perf/aggregate_results.py"
