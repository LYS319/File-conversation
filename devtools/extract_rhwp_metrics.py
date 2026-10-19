"""rhwp(MIT, Copyright (c) 2025-2026 Edward Kim)의 글꼴 폭표(Rust 소스 font_metrics_generated.rs·font_metrics_overlays.rs)를 Python 이 읽는 JSON 으로 옮긴다.
사용자 결정(2026-10-14): 글자 폭 숫자는 쓴다. 출처 기록과 MIT 고지는 루트 THIRD_PARTY_NOTICES.md 4절. 우리 한컴 PDF 측정이 있는 곳은 측정이 우선이고, 이 표는 빈자리 채움·대조용이다.
    python devtools/extract_rhwp_metrics.py [rhwp 소스 폴더=corpus/_ref/rhwp_src] [출력=core/data/rhwp_font_metrics.json.gz]
출력: {"source":…, "fonts":[{"name","bold","italic","em","latin":[[start,end,[폭…]]…],"hangul":{"cho_groups","jung_groups","jong_groups","cho_map","jung_map","jong_map","widths"}|null}…]}
폭 단위는 em/em_size (보통 1000). 한글 음절 폭은 (초성 그룹, 중성 그룹, 종성 그룹) 조합 표 — rhwp `FontMetric::get_width` 와 같은 색인."""
import gzip, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'corpus' / '_ref' / 'rhwp_src'
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'core' / 'data' / 'rhwp_font_metrics.json.gz'
FILES = [SRC / 'src' / 'renderer' / n for n in ('font_metrics_generated.rs', 'font_metrics_overlays.rs')]

ARR = re.compile(r'static\s+(\w+)\s*:\s*\[(u8|u16);\s*\d+\]\s*=\s*\[([^\]]*)\]\s*;', re.S)
RANGES = re.compile(r'static\s+(\w+)\s*:\s*\[LatinRange;\s*\d+\]\s*=\s*\[(.*?)\]\s*;', re.S)
RANGE1 = re.compile(r'LatinRange\s*\{\s*start:\s*(0x[0-9A-Fa-f]+|\d+)\s*,\s*end:\s*(0x[0-9A-Fa-f]+|\d+)\s*,\s*widths:\s*&(\w+)\s*,?\s*\}', re.S)
HANGUL = re.compile(r'static\s+(\w+)\s*:\s*HangulMetric\s*=\s*HangulMetric\s*\{(.*?)\}\s*;', re.S)
ENTRY = re.compile(r'FontMetric\s*\{\s*name:\s*"([^"]*)"\s*,\s*bold:\s*(true|false)\s*,\s*italic:\s*(true|false)\s*,\s*em_size:\s*(\d+)\s*,\s*latin_ranges:\s*&(\w+)\s*,\s*hangul:\s*(None|Some\(&(\w+)\))\s*,?\s*\}', re.S)


def num(s): return int(s, 16) if s.lower().startswith('0x') else int(s)


def main():
    text = '\n'.join(f.read_text(encoding='utf-8') for f in FILES)
    text = re.sub(r'//[^\n]*', '', text)      # 주석(한글 설명·URL)은 파싱에 방해
    arrs = {m.group(1): [int(x) for x in re.findall(r'\d+', m.group(3))] for m in ARR.finditer(text)}
    ranges = {m.group(1): [[num(a), num(b), arrs[w]] for a, b, w in RANGE1.findall(m.group(2))] for m in RANGES.finditer(text)}
    hang = {}
    for m in HANGUL.finditer(text):
        f = dict(re.findall(r'(\w+):\s*([&\w]+)', m.group(2)))
        hang[m.group(1)] = dict(cho_groups=int(f['cho_groups']), jung_groups=int(f['jung_groups']), jong_groups=int(f['jong_groups']),
                                cho_map=arrs[f['cho_map'].lstrip('&')], jung_map=arrs[f['jung_map'].lstrip('&')], jong_map=arrs[f['jong_map'].lstrip('&')], widths=arrs[f['widths'].lstrip('&')])
    fonts = []
    for name, b, i, em, lr, hs, hsym in ENTRY.findall(text):
        fonts.append(dict(name=name, bold=b == 'true', italic=i == 'true', em=int(em), latin=ranges[lr], hangul=hang[hsym] if hsym else None))
    out = dict(source='rhwp v0.8.7 (MIT, Copyright (c) 2025-2026 Edward Kim) src/renderer/font_metrics_generated.rs + font_metrics_overlays.rs', fonts=fonts)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, 'wt', encoding='utf-8', compresslevel=9) as g: json.dump(out, g, ensure_ascii=False, separators=(',', ':'))
    print('글꼴 %d개 (generated + overlay), 한글 표 %d개, 출력 %s (%.2f MB)' % (len(fonts), len(hang), OUT, OUT.stat().st_size / 1e6))


if __name__ == '__main__': main()
