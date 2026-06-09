#!/usr/bin/env python3
"""LNAIME 常駐トレイアプリ（Caffeine 風）。GNOME/Wayland, GTK3 + AyatanaAppIndicator3。
脳(コンテナ)を束ね、どのアプリでもローマ字→変換/校正してクリップボードへ。
"""
import json
import subprocess
import urllib.request

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
from gi.repository import Gdk, Gtk  # noqa: E402

BRAIN = "http://127.0.0.1:8077"
REPO = "/run/media/tonoken3/DATA2/Lna-Lab/LNAIME"
COMPOSE = ["docker", "compose", "-f", f"{REPO}/compose.yaml"]


def api(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BRAIN + path, data, {"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def clip(text: str) -> None:
    cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    cb.set_text(text, -1)
    cb.store()


class ConvertWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="LNAIME 変換")
        self.set_default_size(480, 170)
        self.set_border_width(10)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(box)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("ローマ字で入力（例: bokuhayukigadaisukidesu）")
        self.entry.connect("activate", self.on_convert)
        box.pack_start(self.entry, False, False, 0)

        hb = Gtk.Box(spacing=6)
        b = Gtk.Button(label="変換")
        b.connect("clicked", self.on_convert)
        hb.pack_start(b, False, False, 0)
        self.faithful = Gtk.CheckButton(label="読み忠実保証(lattice)")
        hb.pack_start(self.faithful, False, False, 0)
        box.pack_start(hb, False, False, 0)

        self.result = Gtk.Entry()
        self.result.set_editable(False)
        self.result.set_placeholder_text("変換結果")
        box.pack_start(self.result, False, False, 0)

        self.info = Gtk.Label(label="")
        self.info.set_xalign(0)
        box.pack_start(self.info, False, False, 0)

        cp = Gtk.Button(label="コピー（クリップボードへ）")
        cp.connect("clicked", self.on_copy)
        box.pack_start(cp, False, False, 0)

    def on_convert(self, *_):
        romaji = self.entry.get_text().strip()
        if not romaji:
            return
        try:
            d = api("/convert", {"input": romaji, "faithful": self.faithful.get_active()})
        except Exception as e:
            self.info.set_text(f"エラー: {e}（メニューでサービス起動を）")
            return
        if "error" in d:
            self.info.set_text(f"{d['error']}")
            return
        self.result.set_text(d.get("converted") or "")
        eng = d.get("engine", "")
        f = "✅読み忠実" if d.get("faithful") else "⚠️未保証"
        self.info.set_text(f"[{eng}] {f}")

    def on_copy(self, *_):
        t = self.result.get_text()
        if t:
            clip(t)
            self.info.set_text("クリップボードにコピーしました")


class CheckWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="LNAIME 校正")
        self.set_default_size(560, 420)
        self.set_border_width(10)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(box)

        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(140)
        self.text = Gtk.TextView()
        self.text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sw.add(self.text)
        box.pack_start(sw, False, False, 0)

        b = Gtk.Button(label="校正")
        b.connect("clicked", self.on_check)
        box.pack_start(b, False, False, 0)

        sw2 = Gtk.ScrolledWindow()
        sw2.set_vexpand(True)
        self.out = Gtk.TextView()
        self.out.set_editable(False)
        self.out.set_monospace(True)
        sw2.add(self.out)
        box.pack_start(sw2, True, True, 0)

    def on_check(self, *_):
        buf = self.text.get_buffer()
        s = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        if not s.strip():
            return
        try:
            diags = api("/check", {"text": s}).get("diagnostics", [])
        except Exception as e:
            self.out.get_buffer().set_text(f"エラー: {e}")
            return
        if not diags:
            self.out.get_buffer().set_text("指摘なし。")
            return
        lines = [f"L{d['line']}:{d['col']} [{d['rule']}] 「{d['surface']}」 → 「{d['suggestion']}」"
                 for d in diags]
        self.out.get_buffer().set_text(f"指摘 {len(diags)} 件\n" + "\n".join(lines))


class Tray:
    def __init__(self):
        self.ind = AppIndicator.Indicator.new(
            "lnaime", "input-keyboard",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.ind.set_title("LNAIME")
        self.ind.set_menu(self._menu())
        self.cw = None
        self.kw = None

    def _menu(self):
        m = Gtk.Menu()

        def item(label, cb):
            it = Gtk.MenuItem.new_with_label(label)
            it.connect("activate", cb)
            m.append(it)

        item("変換…", self.open_convert)
        item("校正…", self.open_check)
        m.append(Gtk.SeparatorMenuItem())
        item("サービス起動 (compose up)", self.svc_up)
        item("サービス停止 (compose down)", self.svc_down)
        item("状態を表示", self.status)
        m.append(Gtk.SeparatorMenuItem())
        item("終了", lambda *_: Gtk.main_quit())
        m.show_all()
        return m

    def open_convert(self, *_):
        if not self.cw:
            self.cw = ConvertWindow()
            self.cw.connect("delete-event", lambda *_: (setattr(self, "cw", None), False)[1])
        self.cw.show_all()
        self.cw.present()

    def open_check(self, *_):
        if not self.kw:
            self.kw = CheckWindow()
            self.kw.connect("delete-event", lambda *_: (setattr(self, "kw", None), False)[1])
        self.kw.show_all()
        self.kw.present()

    def svc_up(self, *_):
        subprocess.Popen(COMPOSE + ["--profile", "gpu", "up", "-d"])

    def svc_down(self, *_):
        subprocess.Popen(COMPOSE + ["--profile", "gpu", "down"])

    def status(self, *_):
        try:
            out = subprocess.run(COMPOSE + ["ps", "--format", "{{.Name}}\t{{.Status}}"],
                                 capture_output=True, text=True, timeout=15).stdout.strip()
        except Exception as e:
            out = str(e)
        d = Gtk.MessageDialog(modal=True, message_type=Gtk.MessageType.INFO,
                              buttons=Gtk.ButtonsType.OK, text="LNAIME サービス状態")
        d.format_secondary_text(out or "(コンテナなし)")
        d.run()
        d.destroy()


def main():
    Tray()
    Gtk.main()


if __name__ == "__main__":
    main()
