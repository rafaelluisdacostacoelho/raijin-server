#!/bin/bash
# Gera metricas em formato Prometheus para tamanho dos logs do raijin-server.
# Pode ser usado com node_exporter textfile collector.

set -euo pipefail

LOG_DIR=${RAIJIN_LOG_DIR:-/var/log/raijin-server}
LOG_PATTERN=${RAIJIN_LOG_PATTERN:-raijin-server.log*}
OUTPUT=${RAIJIN_METRIC_FILE:-/var/lib/node_exporter/textfile_collector/raijin_log_size.prom}

# Calcula soma de todos os logs (principal + rotações)
TOTAL_BYTES=0
shopt -s nullglob

METRICS_TMP=$(mktemp)
trap 'rm -f "$METRICS_TMP"' EXIT

for f in "$LOG_DIR"/$LOG_PATTERN; do
  size=$(stat -c%s "$f" 2>/dev/null || echo 0)
  TOTAL_BYTES=$((TOTAL_BYTES + size))
  if [[ "$f" =~ raijin-server\.log(\.\d+)?$ ]]; then
    printf "raijin_log_size_bytes{file=\"%s\"} %d\n" "$(basename "$f")" "$size" >> "$METRICS_TMP"
  fi
done

# Escreve métricas no arquivo final
mkdir -p "$(dirname "$OUTPUT")"
{
  echo "# HELP raijin_log_size_bytes Tamanho dos logs do raijin-server (bytes)"
  echo "# TYPE raijin_log_size_bytes gauge"
  cat "$METRICS_TMP"
  echo "# HELP raijin_log_size_total_bytes Soma dos logs do raijin-server (bytes)"
  echo "# TYPE raijin_log_size_total_bytes gauge"
  echo "raijin_log_size_total_bytes ${TOTAL_BYTES}"
} > "$OUTPUT"
