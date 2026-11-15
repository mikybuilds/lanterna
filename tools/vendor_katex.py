"""Puts KaTeX, which draws formulas in the window, into src/lanterna/ui from its npm package:

    npm pack katex@0.19.1                          # npm checks the package's checksum
    python tools/vendor_katex.py katex-0.19.1.tgz

ui/katex.js   KaTeX with its chemistry (mhchem: \\ce{H2O}) and copy (copy-tex) add-ons, as published;
ui/katex.css  KaTeX's styles with its fonts inside (woff2 as data: URLs), so the window needs no font files next to
              it, whether it opens the page from a file or from a server;
ui/katex-license.txt  KaTeX's license (MIT).
"""
from __future__ import annotations

import base64
import re
import sys
import tarfile
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "src" / "lanterna" / "ui"
JS = ("dist/katex.min.js", "dist/contrib/mhchem.min.js", "dist/contrib/copy-tex.min.js")


def main(tgz: str) -> int:
    with tarfile.open(tgz) as tar:
        files = {m.name.removeprefix("package/"): m for m in tar.getmembers() if m.isfile()}
        read = lambda name: tar.extractfile(files[name]).read()                       # noqa: E731
        version = re.search(r'version:"([^"]+)"', read("dist/katex.min.js").decode()).group(1)
        head = f"/* KaTeX {version} (katex.org; MIT license: katex-license.txt): {{}} */\n"
        js = "".join(head.format(name.rsplit("/", 1)[1]) + read(name).decode().strip() + "\n" for name in JS)

        def font(m: re.Match) -> str:
            data = base64.b64encode(read(f"dist/fonts/{m.group(1)}.woff2")).decode()
            return f'src:url(data:font/woff2;base64,{data}) format("woff2")'
        css = read("dist/katex.min.css").decode()
        css, n = re.subn(r'src:url\(fonts/([\w-]+)\.woff2\) format\("woff2"\)(?:,url\([^)]*\) format\("[a-z]+"\))*', font, css)
        if n != css.count("@font-face") or "url(fonts/" in css:
            print("the fonts in katex.min.css look different than expected: nothing written")
            return 1
        (UI / "katex.js").write_text(js, encoding="utf-8", newline="\n")
        (UI / "katex.css").write_text(head.format("katex.min.css") + css.strip() + "\n", encoding="utf-8", newline="\n")
        (UI / "katex-license.txt").write_bytes(read("LICENSE"))
    print(f"KaTeX {version}: katex.js, katex.css ({n} fonts inside), katex-license.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 else print(__doc__) or 2)
