#!/usr/bin/env bash
# LNAIME 常駐トレイ起動。
# ※ 通常の端末（GNOME端末など, VS Code snap の外）から実行してください。
#    VS Code 内蔵端末は snap 環境で GTK が壊れます（このスクリプトで snap 変数を除去します）。
set -e
cd "$(cd "$(dirname "$0")/.." && pwd)"

# snap(VS Code)汚染の除去 — 通常端末では何も影響しません
unset GTK_EXE_PREFIX GTK_PATH GDK_PIXBUF_MODULE_FILE GIO_MODULE_DIR \
      GI_TYPELIB_PATH LD_LIBRARY_PATH LOCPATH GSETTINGS_SCHEMA_DIR 2>/dev/null || true

exec python3 tray/lnaime_tray.py
