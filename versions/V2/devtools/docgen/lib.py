"""문서 생성 부품: 실제 파일에서 코드 조각을 뽑고, 색칠하고, 번호 배지를 달고, SVG 도식을 그린다."""
import html as H, io, keyword, re, tokenize
from pathlib import Path

ROOT = Path(r'D:\Company_project\File-conversation')
CIRC = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'
esc = lambda s: H.escape(s, quote=False)


# ---------------------------------------------------------------- 코드 조각
def snip(rel, start, n=None, end=None, nth=1):
    """rel 파일에서 start가 들어 있는 줄부터 n줄(또는 end가 나오기 직전까지)을 뽑는다."""
    L = (ROOT / rel).read_text(encoding='utf-8').splitlines()
    hits = [i for i, l in enumerate(L) if start in l]
    assert len(hits) >= nth, f'앵커를 못 찾음: {rel} :: {start}'
    i = hits[nth - 1]
    if n: j = i + n
    elif end: j = next(k for k in range(i + 1, len(L)) if end in L[k])
    else: j = i + 1
    chunk = L[i:j]
    while chunk and not chunk[-1].strip(): chunk.pop()
    return dict(rel=rel, first=i + 1, lines=chunk)


def whole(rel):
    L = (ROOT / rel).read_text(encoding='utf-8').splitlines()
    return dict(rel=rel, first=1, lines=L)


def py_marks(lines):
    """tokenize로 주석·문자열·키워드·숫자의 (시작, 끝, 종류)를 줄마다 모은다. 실패하면 색칠 없이."""
    marks = [[] for _ in lines]
    src = '\n'.join(lines) + '\n'
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            kind = None
            if t.type == tokenize.COMMENT: kind = 'c'
            elif t.type == tokenize.STRING or t.type in (getattr(tokenize, 'FSTRING_START', -1), getattr(tokenize, 'FSTRING_MIDDLE', -1), getattr(tokenize, 'FSTRING_END', -1)): kind = 's'
            elif t.type == tokenize.NUMBER: kind = 'n'
            elif t.type == tokenize.NAME and keyword.iskeyword(t.string): kind = 'k'
            if not kind: continue
            (sr, sc), (er, ec) = t.start, t.end
            for r in range(sr, er + 1):
                if r - 1 >= len(lines): break
                a = sc if r == sr else 0
                b = ec if r == er else len(lines[r - 1])
                if b > a: marks[r - 1].append((a, b, kind))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return marks


def hash_marks(lines):
    """Dockerfile·YAML·TOML: '#' 주석만 색칠."""
    out = []
    for l in lines:
        m = re.search(r'(^|\s)#', l)
        out.append([(m.end() - 1, len(l), 'c')] if m else [])
    return out


def seg(line, marks):
    cls = [None] * len(line)
    for a, b, k in marks:
        for i in range(a, min(b, len(line))): cls[i] = k
    out, i = [], 0
    while i < len(line):
        j = i
        while j < len(line) and cls[j] == cls[i]: j += 1
        text = esc(line[i:j])
        out.append(f'<span class="t{cls[i]}">{text}</span>' if cls[i] else text)
        i = j
    return ''.join(out)


def code(sn, notes=(), lang='py', title=None):
    """sn: snip()/whole() 결과. notes: [(줄 앵커, 설명 HTML), ...] — 앵커가 있는 줄에 ①②… 배지를 단다."""
    lines = sn['lines']
    badge = {}
    for k, (anchor, _) in enumerate(notes, 1):
        li = next((i for i, l in enumerate(lines) if anchor in l), None)
        assert li is not None, f'노트 앵커를 못 찾음: {sn["rel"]} :: {anchor}'
        badge.setdefault(li, []).append(k)
    marks = py_marks(lines) if lang == 'py' else hash_marks(lines)
    body = ''.join(
        f'<span class="l{" hl" if i in badge else ""}"><i class="g" data-ln="{sn["first"] + i}" data-b="{"".join(CIRC[k - 1] for k in badge.get(i, []))}"></i>{seg(l, marks[i])}</span>'
        for i, l in enumerate(lines))
    last = sn['first'] + len(lines) - 1
    head = f'<div class="ch"><b>{esc(sn["rel"])}</b><span>{sn["first"]}~{last}행' + (f' · {esc(title)}' if title else '') + '</span></div>'
    nts = ''
    if notes:
        nts = '<ol class="notes">' + ''.join(f'<li><b class="bd">{CIRC[k]}</b><div>{t}</div></li>' for k, (_, t) in enumerate(notes)) + '</ol>'
    return f'<div class="code">{head}<pre><code>{body}</code></pre>{nts}</div>'


# ---------------------------------------------------------------- SVG 도식
DEFS = ('<defs>'
        '<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="ahp"/></marker>'
        '<marker id="ahx" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="ahpx"/></marker>'
        '</defs>')


def svg(w, h, inner, label):
    return f'<svg class="dg" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">{DEFS}{inner}</svg>'


def node(x, y, w, h, lines, cls='n1', dashed=False):
    cy = y + h / 2 - (len(lines) - 1) * 9 + 5
    t = ''.join(f'<text x="{x + w / 2}" y="{cy + i * 18}" text-anchor="middle" class="{"tb" if i == 0 else "ts"}">{esc(s)}</text>' for i, s in enumerate(lines))
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" class="nd {cls}"' + (' stroke-dasharray="6 4"' if dashed else '') + f'/>{t}'


def group(x, y, w, h, title, cls='g1'):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" class="gp {cls}"/>'
            f'<text x="{x + 14}" y="{y + 22}" class="gt">{esc(title)}</text>')


def edge(pts, label=None, lx=None, ly=None, dashed=False, bad=False, anchor='middle'):
    d = 'M' + ' L'.join(f'{x} {y}' for x, y in pts)
    cls = 'ed bad' if bad else 'ed'
    s = f'<path d="{d}" class="{cls}" fill="none"' + (' stroke-dasharray="6 4"' if dashed else '') + f' marker-end="url(#{"ahx" if bad else "ah"})"/>'
    if label:
        mx = lx if lx is not None else (pts[0][0] + pts[-1][0]) / 2
        my = ly if ly is not None else (pts[0][1] + pts[-1][1]) / 2 - 6
        s += f'<text x="{mx}" y="{my}" text-anchor="{anchor}" class="el">{esc(label)}</text>'
    return s


def note(x, y, lines, anchor='start', cls='ts'):
    return ''.join(f'<text x="{x}" y="{y + i * 17}" text-anchor="{anchor}" class="{cls}">{esc(s)}</text>' for i, s in enumerate(lines))
