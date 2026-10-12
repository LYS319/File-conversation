"""HWP 5.0(.hwp, OLE2) -> 단일 HTML. 사진은 JPEG data URI로 넣는다.
claude.ai 채팅의 Claude가 샌드박스에서 즉석으로 짠 파서(cfb.py + convert.py + 번호/글머리/들여쓰기 패치)를 그대로 복원한 것.
# ponytail: 그 문서 한 건에 맞춘 프로토타입. 구역은 Section0만, 표 테두리·폭 단순화, span에 글꼴 없음, 쪽 설정·머리글·바닥글 없음.
#           보강은 일반화 시험(근무계획서 .hwp)에서 나온 차이 목록 순서로 한다.
#           모듈 전역 상태를 쓰므로 프로세스당 변환 1건씩 호출하는 것을 전제로 한다(convert()는 호출마다 상태를 다시 읽음)."""
import base64, html, io, os, re, struct, sys, zlib
from pathlib import Path
from PIL import Image

MAX_BYTES = 100 * 1024 * 1024            # 회의록 66MB를 받아들이는 상한 (계획서 8장 입력 방어)
MAX_STREAM = 512 * 1024 * 1024           # 스트림 하나를 푼 크기 상한. 회의록의 BMP 사진은 장당 70MB라 100MB로 잡으면 정상 문서가 막힌다


class CFB:
    """OLE2 복합 파일 리더 (olefile 없이)"""
    def __init__(self, path):
        self.d = Path(path).read_bytes()
        d = self.d
        if d[:8] != bytes.fromhex('D0CF11E0A1B11AE1'): raise ValueError('OLE2 파일이 아님')
        self.ss = 1 << struct.unpack_from('<H', d, 30)[0]
        self.mss = 1 << struct.unpack_from('<H', d, 32)[0]
        nfat, = struct.unpack_from('<I', d, 44)
        firstdir, = struct.unpack_from('<I', d, 48)
        self.cutoff, = struct.unpack_from('<I', d, 56)
        fminifat, nminifat, fdifat, ndifat = struct.unpack_from('<IIII', d, 60)
        difat = list(struct.unpack_from('<109I', d, 76))
        s = fdifat
        while s not in (0xFFFFFFFE, 0xFFFFFFFF) and ndifat:
            sec = self.sec(s); n = self.ss // 4
            v = struct.unpack('<%dI' % n, sec); difat += v[:-1]; s = v[-1]; ndifat -= 1
        difat = [x for x in difat if x < 0xFFFFFFFA][:nfat]
        fat = b''.join(self.sec(x) for x in difat)
        self.fat = struct.unpack('<%dI' % (len(fat) // 4), fat)
        dirdata = self.chain(firstdir)
        self.entries = []
        for i in range(len(dirdata) // 128):
            e = dirdata[i * 128:(i + 1) * 128]
            nl, = struct.unpack_from('<H', e, 64)
            name = e[:max(nl - 2, 0)].decode('utf-16le')
            typ = e[66]; l, r, c = struct.unpack_from('<III', e, 68)
            start, = struct.unpack_from('<I', e, 116); size, = struct.unpack_from('<Q', e, 120)
            if self.ss == 512: size &= 0xFFFFFFFF
            self.entries.append(dict(name=name, type=typ, left=l, right=r, child=c, start=start, size=size))
        root = self.entries[0]
        self.ministream = self.chain(root['start'])[:root['size']] if root['start'] < 0xFFFFFFFA else b''
        mf = self.chain(fminifat) if nminifat else b''
        self.minifat = struct.unpack('<%dI' % (len(mf) // 4), mf)
        self.paths = {}
        self._walk(root['child'], '', set())

    def sec(self, i): o = (i + 1) * self.ss; return self.d[o:o + self.ss]

    def chain(self, s):
        out = []
        for _ in range(len(self.fat) + 1):                   # FAT 순환(손상·악의 파일) 방어
            if s >= 0xFFFFFFFA: return b''.join(out)
            out.append(self.sec(s)); s = self.fat[s]
        raise ValueError('FAT 순환')

    def _walk(self, i, prefix, seen):
        if i >= len(self.entries) or i in seen: return
        seen.add(i)
        e = self.entries[i]
        self._walk(e['left'], prefix, seen); self._walk(e['right'], prefix, seen)
        p = prefix + '/' + e['name']; self.paths[p] = i
        if e['type'] in (1, 5): self._walk(e['child'], p, seen)

    def read(self, p):
        e = self.entries[self.paths[p]]
        if e['size'] < self.cutoff:
            out = []; s = e['start']
            for _ in range(len(self.minifat) + 1):
                if s >= 0xFFFFFFFA: break
                o = s * self.mss; out.append(self.ministream[o:o + self.mss]); s = self.minifat[s]
            return b''.join(out)[:e['size']]
        return self.chain(e['start'])[:e['size']]


# ---- 문서 상태 (load()가 채운다)
c = COMP = nhangul = None
faces = []; bins = []; borderfills = []; charshapes = []; parashapes = []; numberings = []; tabdefs = []
NUMC = {}
PGNP = [None]       # 쪽 번호 위치(pgnp 컨트롤): (속성, 앞 장식, 뒤 장식)
MASTER = [None]     # 바탕쪽을 그리는 동안 (본문 왼쪽 여백 pt, 본문 위쪽 여백 pt)
_SL = os.environ.get('STORED_LAYOUT', '')
STORED = _SL in ('1', 'all', 'lines')       # 저장된 줄 끊김대로
STORED_P = _SL in ('1', 'all', 'pages')     # 저장된 쪽 시작대로      # 실험: 한컴이 저장한 줄 끊김·쪽 시작(PARA_LINE_SEG)대로
LB = chr(1) + 'LB'       # 저장된 줄 바꿈 자리 표시
SKIPPED = []        # 읽지 못해 뺀 그림의 오류 이름(변환 끝에 경고로 알린다)
PAGEM = [0, 0]      # 지금 구역의 본문 왼쪽·위쪽 여백 pt(종이 기준 좌표를 본문 기준으로 바꿀 때)
LAST_HF = {'head': (None, None), 'foot': (None, None)}      # 앞 구역의 (홀수 쪽, 짝수 쪽) 머리말·꼬리말(구역에서 새로 안 나오면 이어 씀)
HFM = {'head': [], 'foot': []}      # 머리말·꼬리말 정의 기록: (걸린 최상위 문단 번호, 적용 쪽 0 양쪽·1 짝수·2 홀수, HTML). 같은 쪽에 정의가 둘이면 나중 것이 이긴다
CUR = [0]       # 지금 그리는 최상위 문단 번호(HFM 에 적을 값)
OUTLINE = [1]       # 개요 번호가 쓰는 번호 모양 번호(구역 정의의 '번호 문단 모양 ID'). 기본 1


def num_shape(n, shape):
    """번호 모양(0 숫자, 1 ①, 2·3 로마자, 4·5 영문, 8 가나다, 9 ㉮)에 맞춰 n 번째 번호를 글자로. 모르는 모양은 숫자."""
    if shape == 1 and 1 <= n <= 20: return chr(0x2460 + n - 1)
    if shape in (2, 3):
        s, r = '', n
        for v, t in ((1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')):
            while r >= v: s += t; r -= v
        return s if shape == 2 else s.lower()
    if shape in (4, 5) and 1 <= n <= 26: return chr((64 if shape == 4 else 96) + n)
    if shape == 8 and 1 <= n <= 14: return '가나다라마바사아자차카타파하'[n - 1]
    if shape == 9 and 1 <= n <= 14: return chr(0x326E + n - 1)
    if shape in (6, 7) and 1 <= n <= 26: return chr((0x24B6 if shape == 6 else 0x24D0) + n - 1)        # Ⓐ ⓐ
    if shape == 10 and 1 <= n <= 14: return 'ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ'[n - 1]
    if shape == 11 and 1 <= n <= 14: return chr(0x3260 + n - 1)       # ㉠
    if shape == 12 and 1 <= n <= 10: return '일이삼사오육칠팔구십'[n - 1]
    if shape == 13 and 1 <= n <= 10: return '一二三四五六七八九十'[n - 1]
    if shape == 14 and 1 <= n <= 10: return chr(0x3220 + n - 1)       # ㈠ 계열(한자 괄호 숫자)
    return str(n)


HF = {'head': [], 'foot': []}       # 머리말·꼬리말 내용(쪽마다 반복은 못 하고 본문 맨 앞/끝에 한 번 둔다)
IMAGES = []


def dec(b, force=None):
    if force is False or not (COMP if force is None else force): return b
    d = zlib.decompressobj(-15); out = d.decompress(b, MAX_STREAM + 1)      # 압축 폭탄 방어: 푼 크기가 상한을 넘으면 거부
    if len(out) > MAX_STREAM: raise ValueError('압축을 푼 크기가 한도(스트림당 512MB)를 넘음')
    if not d.eof: raise zlib.error('incomplete or truncated stream')       # zlib.decompress와 같은 동작 유지
    return out


def records(b):
    i = 0; out = []
    while i < len(b):
        h, = struct.unpack_from('<I', b, i); i += 4
        tag = h & 0x3FF; lvl = (h >> 10) & 0x3FF; sz = h >> 20
        if sz == 0xFFF: sz, = struct.unpack_from('<I', b, i); i += 4
        out.append((tag, lvl, b[i:i + sz])); i += sz
    return out


def load(src):
    """DocInfo(글꼴·글자/문단 모양·테두리/배경·번호매기기·BinData)를 읽는다"""
    global c, COMP, nhangul
    if Path(src).stat().st_size > MAX_BYTES: raise ValueError('파일이 너무 큼 (상한 100MB)')
    c = CFB(src)
    fh = c.read('/FileHeader')
    if fh[:17] != b'HWP Document File': raise ValueError('HWP 5.0 파일이 아님')
    flags, = struct.unpack_from('<I', fh, 36)
    if flags & 0b10110: raise ValueError('암호화/배포용/DRM 문서는 지원하지 않음')      # bit1 암호, bit2 배포용, bit4 DRM
    COMP = flags & 1
    for L in (faces, bins, borderfills, charshapes, parashapes, numberings, tabdefs, IMAGES): L.clear()
    SKIPPED.clear(); NUMC.clear(); HF['head'].clear(); HF['foot'].clear(); HFM['head'].clear(); HFM['foot'].clear(); OUTLINE[0] = 1; PGNP[0] = None
    di = records(dec(c.read('/DocInfo')))
    idmap = next(p for t, _, p in di if t == 17)
    _, nhangul = struct.unpack_from('<II', idmap, 0)
    fcounts = struct.unpack_from('<7I', idmap, 4); fstart = [sum(fcounts[:k]) for k in range(7)]      # 아이디 매핑(표 16): 언어별 글꼴 개수. FACE_NAME 은 한글·영어·한자… 차례로 이어 붙어 있다
    for t, l, p in di:
        if t == 19:
            n, = struct.unpack_from('<H', p, 1); faces.append(p[3:3 + 2 * n].decode('utf-16le'))
        elif t == 18:
            prop, bid, n = struct.unpack_from('<HHH', p, 0); ext = p[6:6 + 2 * n].decode('utf-16le')
            bins.append(dict(id=bid, ext=ext, comp=(prop >> 4) & 3))
        elif t == 20:
            fill = None
            ft, = struct.unpack_from('<I', p, 32)
            if ft & 1 and len(p) >= 40:
                col, = struct.unpack_from('<I', p, 36)
                if col != 0xFFFFFFFF: fill = col
            # 테두리 4개: 왼·오·위·아래 순서, 각 (종류 1B, 굵기 1B, 색 RGB 3B+1B). 바이트는 hwp-cli 가 같은 문서에서 읽은 값과 한 줄씩 대조해 확인했다
            borders = [(p[2 + 6 * k], p[3 + 6 * k], '#%02x%02x%02x' % (p[4 + 6 * k], p[5 + 6 * k], p[6 + 6 * k])) for k in range(4)] if len(p) >= 26 else None
            grad = None
            if ft & 4 and len(p) >= 61:        # 그라데이션: 종류 1B(1 선형), 각도 4B, 중심 x·y 4B씩, 번짐 4B, 색 개수 4B, (3개 이상이면 위치 4B씩), 색 4B씩. 선형만 쓴다
                ncol, = struct.unpack_from('<I', p, 53); base = 57 + (4 * ncol if ncol > 2 else 0)
                if p[36] == 1 and 2 <= ncol <= 16 and len(p) >= base + 4 * ncol:
                    grad = (struct.unpack_from('<i', p, 37)[0], [rgb(struct.unpack_from('<I', p, base + 4 * k)[0]) for k in range(ncol)])
            borderfills.append(dict(fill=fill, borders=borders, grad=grad))
        elif t == 21:
            face0, = struct.unpack_from('<H', p, 0)
            size, prop = struct.unpack_from('<iI', p, 42)
            color, = struct.unpack_from('<I', p, 52)
            # 공식 문서(글 문서 파일 형식 5.0, 표 33): 언어 7칸(한글·영어·한자·일어·기타·기호·사용자)마다 글꼴 번호 WORD[7]@0, 장평 UINT8[7]@14, 자간 INT8[7]@21, 상대 크기 UINT8[7]@28, 글자 위치 INT8[7]@35
            langs = []
            for k in range(7):
                fid, = struct.unpack_from('<H', p, 2 * k); gi = fstart[k] + fid
                langs.append(dict(face=faces[gi] if fid < fcounts[k] and gi < len(faces) else None, ratio=p[14 + k] or 100,
                                  spacing=struct.unpack_from('<b', p, 21 + k)[0], rel=p[28 + k] or 100, pos=struct.unpack_from('<b', p, 35 + k)[0]))
            charshapes.append(dict(face=langs[0]['face'], langs=langs,
                spacing=langs[0]['spacing'],      # 자간(%): 한글 칸. 서식 문서는 -5~-9 를 흔히 써서 글이 5~8% 좁다
                size=size / 100, bold=bool(prop & 2), italic=bool(prop & 1), underline=(prop >> 2) & 3, sup=bool(prop >> 15 & 1), sub=bool(prop >> 16 & 1),
                color=color, strike=bool((prop >> 18) & 7) and (prop >> 26) & 0xF != 15))      # 취소선 모양 15('3D')는 "취소선 없음" 자리표시(한컴이 안 그림; HWPX 에도 strikeout shape=3D 로 같이 나옴)
        elif t == 23:
            q = 0; levels = []
            for lv in range(7):
                # 문단 머리 정보(공식 표 39·40): 속성 4B(비트2 너비 따름, 비트3 자동 내어쓰기, 비트4 거리 종류 0=글자 크기 %·1=값, 비트5~ 번호 모양), 너비 보정 2B, 본문과의 거리 2B, 글자 모양 4B
                pr, = struct.unpack_from('<I', p, q); dist, = struct.unpack_from('<h', p, q + 6); q += 12
                n, = struct.unpack_from('<H', p, q); q += 2
                levels.append(dict(fmt=p[q:q + 2 * n].decode('utf-16le'), shape=(pr >> 5) & 0x1F, hang=bool(pr & 8), dist=dist, dist_abs=bool(pr & 16))); q += 2 * n
            numberings.append(levels)
        elif t == 25:
            prop, = struct.unpack_from('<I', p, 0)
            left, right, indent, top, bottom, ls = struct.unpack_from('<iiiiii', p, 4)
            parashapes.append(dict(head=(prop >> 23) & 3, level=(prop >> 25) & 7, numid=struct.unpack_from('<H', p, 30)[0],
                align=(prop >> 2) & 7, left=left, right=right, indent=indent, top=top, bottom=bottom, ls=ls, lstype=prop & 3,
                tab=struct.unpack_from('<H', p, 28)[0], widow=bool(prop >> 16 & 1), bw=not prop >> 7 & 1,      # 비트 7 = 한글 줄 나눔 기준: 1 어절(KEEP_WORD)·0 글자(BREAK_WORD) — hwp-cli 가 만든 HWPX breakNonLatinWord 와 문단 모양 2,414개 전부 일치(공식 문서와 반대)
                bf=struct.unpack_from('<H', p, 32)[0], bsp=struct.unpack_from('<4h', p, 34), pbreak=bool(prop >> 19 & 1)))      # 문단 테두리/배경 ID·테두리 간격 4(왼·오·위·아래)·'문단 앞에서 항상 쪽 나눔'(공식 표 43)
        elif t == 22:        # 탭 정의: 속성(비트1 = 문단 오른쪽 끝 자동 탭), 탭 개수, 탭마다 (위치, 종류 0 왼·1 오른·2 가운데, 채움선 종류)
            tattr, tn = struct.unpack_from('<II', p, 0)
            tabdefs.append((tattr, [struct.unpack_from('<IBB', p, 8 + 8 * k) for k in range(tn)]))


def rgb(v): return '#%02x%02x%02x' % (v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF)


def bindata_uri(bid):
    """그림 번호 -> 웹용 JPEG data URI. 읽을 수 없는 그림(벡터 WMF·EMF·SVG, 깨진 첨부, 없는 번호)은 None — 한 장 때문에 문서 전체 변환이 실패하지 않게 SKIPPED 에 적어 둔다."""
    try:
        b = next(x for x in bins if x['id'] == bid)
        raw = c.read('/BinData/BIN%04X.%s' % (bid, b['ext']))
        data = dec(raw, None if b['comp'] == 0 else (b['comp'] == 1))
        im = Image.open(io.BytesIO(data)).convert('RGB')
    except Exception as e:
        SKIPPED.append(type(e).__name__); return None
    IMAGES.append((bid, im.size))
    im.thumbnail((1400, 1400))
    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=85, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


# ---- 본문 텍스트
EXT = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}; INL = {4, 5, 6, 7, 8, 9, 19, 20}
PUA = {0xF09F: '•', 0xF09E: '·', 0xF0A7: '▪', 0xF0A0: '▪', 0xF0D8: '➢', 0xF0FC: '✔', 0xF0B7: '•',
       0xF0854: '『', 0xF0855: '』', 0xF0039: '⬅', 0xF003B: '⬇'}      # 뒤 4개: 보조 평면 사설 문자. 공고문을 한컴 렌더로 그려 모양을 확인했다
# 아래 36개는 rhwp(https://github.com/edwardkim/rhwp, MIT)의 src/renderer/hancom_pua.rs 에 있는 "한컴 PDF 대조로 확인된" 표를 그대로 가져온 것이다.
# 그중 U+F02EC(◇)·U+F03FF(□)는 우리 점검 문서(육아기 근로시간 단축 신청서)에서도 같은 자리에 나왔다. 나머지는 rhwp 의 검증을 믿고 쓴다.
# U+F53A 는 한양 PUA(옛한글 표, KTUG HanyangPuaTableProject·퍼블릭 도메인)에서 'ᄒᆞᆫ'(ᄒ + 아래아 + ᆫ)이다. rhwp 가 한컴 PDF 로 확인(옛한글 표시는 글꼴 지원이 필요).
PUA[0xF53A] = 'ᄒᆞᆫ'
PUA[0xF071] = '❑'      # HY헤드라인M 의 제목 기호. 공문서 양식에서 hwp-cli 렌더가 ❑ 로 그린 것을 확인(같은 문서의 다른 제목은 진짜 글자 U+2751 ❑)
PUA[0xF06D] = '❍'      # 휴먼명조의 2단계 기호. hwp-cli 렌더는 안 그려서, 사용자가 한컴 한글에서 ❍ 로 보임을 직접 확인(2026-10-07)
# PUA 는 글꼴별 사적 영역이라 코드 범위로 뜻을 짐작하면 안 된다 — 새 항목은 실제 문서와 한컴 PDF 로 확인한 것만 넣는다(rhwp 도 같은 원칙).
PUA.update({0xF0090: '✺', 0xF012B: '(인)', 0xF0288: '⓪', 0xF0289: '①', 0xF028A: '②', 0xF028C: '④', 0xF028D: '⑤', 0xF028E: '⑥', 0xF028F: '⑦',
            0xF0290: '⑧', 0xF0291: '⑨', 0xF02EC: '◇', 0xF02FB: '▸', 0xF02FC: '►', 0xF031C: '■', 0xF03A0: '↵', 0xF03A7: '⊟', 0xF03A8: '⊞',
            0xF03C5: '□', 0xF03DA: '□', 0xF03EF: '한', 0xF03F0: '글', 0xF03F1: '과', 0xF03F2: '컴', 0xF03F3: '퓨', 0xF03F4: '터', 0xF03FF: '□',
            0xF0806: '┌', 0xF0807: '┬', 0xF0808: '┐', 0xF080C: '└', 0xF080E: '┘', 0xF0810: '│', 0xF081C: '┈', 0xF0832: '═', 0xF0848: '━'})


def para_text(b):
    s = struct.unpack('<%dH' % (len(b) // 2), b); i = 0; out = []
    while i < len(s):
        ch = s[i]
        if ch < 32:
            if ch in EXT or ch in INL:
                if ch == 9: out.append((i, '\t'))
                elif ch in EXT: out.append((i, ('CTRL', bytes(b[2 * i + 2:2 * i + 6])[::-1].decode('latin1'))))
                i += 8; continue
            if ch == 10: out.append((i, '\n'))
            elif ch in (24,): out.append((i, '-'))
            elif ch in (30, 31): out.append((i, ' '))
            i += 1; continue
        if 0xD800 <= ch < 0xDC00 and i + 1 < len(s) and 0xDC00 <= s[i + 1] < 0xE000:     # UTF-16 대리쌍 = 보조 평면 글자 한 개(예: U+F0039)
            cp = 0x10000 + ((ch - 0xD800) << 10) + (s[i + 1] - 0xDC00)
            out.append((i, PUA.get(cp, chr(cp)))); i += 2; continue
        out.append((i, '�' if 0xD800 <= ch < 0xE000 else PUA.get(ch, chr(ch)))); i += 1     # 짝 없는 대리 조각은 대체 문자(그대로 두면 파일을 쓸 때 오류)
    return out


ALIGN = {0: 'justify', 1: 'left', 2: 'right', 3: 'center', 4: 'justify', 5: 'justify'}


def hu(v): return v / 75  # HWPUNIT -> px (7200/inch, 96dpi)


# 한컴 글꼴 대 우리가 대신 쓰는 나눔 글꼴의 한글 글자 폭 차이(em). 한컴 PDF 낱말 폭 대 우리 PDF 낱말 폭의 비율(devtools/font_width.py, 공개 문서+사용자 문서 136건)에서 (비율-1)×0.95, 한 번 적용해 다시 재고 남은 비율만큼 한 번 더 고쳤다(전체 비율 0.5~2% 이내).
# 나눔 글꼴의 한글 글자가 1em 보다 좁아 같은 글이 한컴보다 3~6% 짧았고, 줄이 늦게 꺾여 쪽 수·글 위치가 어긋났다. 영문은 Liberation(폭 호환)이라 비율 0.999 로 보정이 필요 없다.
# 글자 폭 차이는 장평(가로 비율)만큼 같이 줄어든다: 장평 70%·26pt 제목에서 보정을 그대로 더하면 한컴보다 넓어져 줄이 하나 더 생겼다(issue2004_cell_image_stack) → 장평을 곱한다.
HANGUL_DELTA = {'함초롬바탕': 0.024, '함초롬돋움': 0.039, '휴먼명조': 0.065, '맑은 고딕': 0.056, 'Malgun Gothic': 0.056, '한컴바탕': 0.056, '굴림': 0.069, '굴림체': 0.074, 'Gulim': 0.069, 'GulimChe': 0.074,
                '바탕': 0.050, '바탕체': 0.065, 'Batang': 0.050, 'BatangChe': 0.065, '돋움': 0.061, '돋움체': 0.062, 'Dotum': 0.061, 'DotumChe': 0.062, 'HY헤드라인M': 0.073, 'HY견고딕': 0.063, '한양견고딕': 0.062}


# 글꼴 자체가 굵게 디자인된 한컴·한양 글꼴(HY헤드라인M 은 '굵게' 속성 없이도 한컴에서 굵게 보인다). 이 글꼴이 없는 PC·나눔 글꼴 대체 PDF 는 보통 굵기로 나와 제목이 약해졌다 → 굵게 속성이 없어도 굵게 준다.
# font-synthesis-weight:none = 진짜 그 글꼴이 있으면 인위적으로 더 굵히지 않는다(굵은 글꼴이 따로 있는 대체 글꼴만 굵어짐).
HEAVY_FACE = re.compile(r'헤드라인|견고딕|태고딕|Black|Heavy|ExtraBold|HY[가-힣]+B$')


def mid_dot(doc):
    """가운뎃점 'ㆍ'(U+318D, 원래는 옛한글 아래아)은 글꼴마다 모양이 다르다. 한컴(바탕)은 가운데의 동그라미인데 윈도 브라우저는 대체 글꼴(맑은 고딕)의 아래아 모양 '、' 로 그린다(공고·법령 문서에 흔함).
    글자는 그대로 두고 바탕 글꼴로 그리게 감싼다(`.mid`). 컨테이너 PDF 에서는 바탕 → 나눔명조라 전과 같다. <style>·<title> 안은 건드리지 않는다."""
    if 'ㆍ' not in doc: return doc
    out, skip = [], False
    for tok in re.split(r'(<[^>]*>)', doc):
        if tok[:1] == '<':
            low = tok[:9].lower()
            if low.startswith(('<style', '<title')): skip = True
            elif low.startswith(('</style', '</title')): skip = False
        elif not skip and 'ㆍ' in tok: tok = tok.replace('ㆍ', '<span class="mid">ㆍ</span>')
        out.append(tok)
    return ''.join(out)


def heavy_css(face, bold):
    return ['font-weight:700;font-synthesis-weight:none'] if not bold and face and HEAVY_FACE.search(face) else []


def family(face):
    """글꼴 이름 -> font-family. 컨테이너에서는 fonts.conf 가 한컴 글꼴을 나눔 글꼴로 바꿔 준다. 못 찾을 때를 위해 고딕/명조 계열만 덧붙인다."""
    face = re.sub(r'''["'<>&;]''', '', face)
    return "font-family:'%s',%s" % (face, 'sans-serif' if re.search('돋움|고딕|굴림|Gothic|Sans|헤드라인|산세리프', face) else 'serif')


def form_text(ctl):
    """양식 개체(체크박스 등): 모양은 못 그리고 기호 + 설명 글만 남긴다. 속성은 'Caption:wstring:<글자수>:<글>', 'Value:int:<0|1>' 꼴의 글로 저장돼 있다."""
    f = next((ch.p for ch in ctl.ch if ch.tag == 91), b'')
    t = f[8:].decode('utf-16le', 'replace')
    m = re.search(r'Caption:wstring:(\d+):', t)
    cap = t[m.end():m.end() + int(m.group(1))] if m else ''
    v = re.search(r'Value:int:(\d+)', t[m.end():] if m else t)
    mark = {'+cbt': ('☐', '☑'), '+rbt': ('○', '◉')}.get(f[:4][::-1].decode('latin1'))
    return (mark[bool(v and v.group(1) != '0')] + ' ' if mark else '') + cap


HALF = r'[\x21-\x7e\s -ɏ]'


def form_box(ctl):
    """입력 상자(+edt)·누름 단추(+pbt)·콤보 상자(+cob)는 기호로 못 나타내니 테두리·배경이 있는 상자로 그린다(크기는 개체 머리의 폭·높이, 배경은 BackColor). 그 밖은 None."""
    f = next((ch.p for ch in ctl.ch if ch.tag == 91), b'')
    kind = f[:4][::-1].decode('latin1')
    if kind not in ('+edt', '+pbt', '+cob') or len(ctl.p) < 24: return None
    t = f[8:].decode('utf-16le', 'replace'); w, h = struct.unpack_from('<II', ctl.p, 16)
    m = re.search(r'Caption:wstring:(\d+):', t); cap = t[m.end():m.end() + int(m.group(1))] if m else ''
    b = re.search(r'BackColor:int:(\d+)', t); bg = rgb(int(b.group(1))) if b else '#fff'
    return ('<span style="display:inline-block;box-sizing:border-box;width:%gpt;height:%gpt;line-height:%gpt;border:1px solid #7f7f7f;background:%s;vertical-align:middle;overflow:hidden;'
            'text-align:%s;font-size:9pt;padding:0 .3em">%s</span>') % (w / 100, h / 100, max(h / 100 - 2, 8), bg, 'center' if kind == '+pbt' else 'left', html.escape(cap) + (' ▾' if kind == '+cob' else ''))


def lang_of(ch):
    """글자가 속한 언어 칸: 0 한글, 1 영어(ASCII·라틴), 2 한자, 3 일어, 4 기타, 5 기호. 공백·탭·줄바꿈은 None(앞뒤 글자 묶음에 붙인다)."""
    o = ord(ch)
    if ch in ' \t\n ': return None
    if 0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F or 0xA960 <= o <= 0xA97F or 0xD7B0 <= o <= 0xD7FF or 0x3000 <= o <= 0x303F: return 0
    if o < 0x250: return 1
    if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF: return 2
    if 0x3040 <= o <= 0x30FF: return 3
    if 0x2000 <= o <= 0x2BFF or 0xE000 <= o <= 0xF8FF or o >= 0xF0000: return 5
    return 4


def script_runs(s):
    """글을 언어 칸이 같은 토막으로 나눈다 -> [(언어, 글)]. 공백류는 현재 토막에 붙는다(처음이면 첫 글자의 토막에)."""
    runs = []; cur = None; pend = ''
    for ch in s:
        k = lang_of(ch)
        if k is None:
            if runs: runs[-1][1] += ch
            else: pend += ch
        elif runs and runs[-1][0] == k: runs[-1][1] += ch
        else: runs.append([k, pend + ch]); pend = ''
    if pend: runs.append([0, pend])
    return [(k, t) for k, t in runs]


def spacing_css(a, b):
    """글자 간격 CSS 조각 목록. a = 문서에 적힌 자간·장평(em), b = 글꼴 폭 보정(HANGUL_DELTA, em).
    b 는 letter-spacing 에 섞지 않고 `--hd`(+ a 가 있으면 `--ls`)로 따로 적는다 — 나눔 글꼴로 찍는 PDF 에서만 더해야 해서다(convert.PDF_CSS 가 둘을 더한다).
    HTML 을 브라우저로 보면 맑은 고딕·굴림 같은 진짜 한컴 글꼴이 이미 한컴 폭이라, 보정까지 섞으면 글이 5~7% 넓어져 줄이 먼저 꺾인다(공고문 '[공급기업]' 의 '업' 이 아래로 내려감, 쪽 14→12)."""
    st = []
    if a: st.append('letter-spacing:%gem' % a)
    if b: st.append('--hd:%gem' % b + (';--ls:%gem' % a if a else ''))
    return st


def span_style(cs, lang=0, half=False):
    L = cs['langs'][lang]; size = cs['size'] * L['rel'] / 100
    if cs['sup'] or cs['sub']: size *= 0.7
    st = ['font-size:%gpt' % size]
    if L['face']: st.append(family(L['face']))
    # 자간은 글자 폭의 %, 장평(가로 비율)은 폭을 그만큼 줄이므로 같은 식으로 합친다. 반각(영문·숫자)은 폭이 전각의 절반이라 em 으로는 절반
    st += spacing_css((L['spacing'] + L['ratio'] - 100) / (200 if half else 100), 0 if half or lang else HANGUL_DELTA.get(L['face'] or '', 0) * L['ratio'] / 100)
    if L['pos']: st.append('position:relative;top:%gem' % (-L['pos'] / 100))      # 글자 위치(%): 양수가 위로
    if cs['sup']: st.append('vertical-align:super')
    if cs['sub']: st.append('vertical-align:sub')
    if cs['bold']: st.append('font-weight:700')
    else: st += heavy_css(L['face'], False)
    if cs['italic']: st.append('font-style:italic')
    deco = (['underline'] if cs['underline'] == 1 else ['overline'] if cs['underline'] == 3 else []) + (['line-through'] if cs['strike'] else [])
    if deco: st.append('text-decoration:' + ' '.join(deco))
    if cs['color'] & 0xFFFFFF: st.append('color:' + rgb(cs['color']))
    return ';'.join(st)


class Node:
    def __init__(s, tag, lvl, p): s.tag, s.lvl, s.p, s.ch = tag, lvl, p, []


def tree(recs):
    root = Node(-1, -1, b''); stack = [root]
    for t, l, p in recs:
        n = Node(t, l, p)
        while stack[-1].lvl >= l: stack.pop()
        stack[-1].ch.append(n); stack.append(n)
    return root


def float_obj(ctl):
    """글 앞(3)·글 뒤(2)에 떠 있는 개체(속성 비트 21~23)는 자리를 차지하지 않는다 — 한컴은 뒤따르는 문단을 바로 이어 놓고, 겹쳐 놓을 자리를 빈 줄로 비워 둔다
    (근무계획서: 앵커 줄 14pt 다음 문단이 곧바로 22.4pt 에서 시작. 표준 공문 양식: 선 도형이 든 문단의 줄이 그대로 남음). 공식 문서 표 70 의 값 이름(Tight=1, TopAndBottom=3…)은
    실제 파일과 달라, 실제는 0 어울림·1 자리 차지·2 글 뒤로·3 글 앞으로. 위치는 왼쪽·위 정렬일 때만: 세로·가로 기준이 모두 문단/단이면 문단 맨 위에서의 오프셋,
    모두 종이/쪽이면 쪽 안 절대 위치(WeasyPrint 의 absolute 는 쪽 본문 영역이 원점). 반환: '%s' 자리에 개체 HTML 을 넣을 문자열, 아니면 None(제자리에 흘림)."""
    if len(ctl.p) < 16 or MASTER[0]: return None
    attr, = struct.unpack_from('<I', ctl.p, 4)
    vrel, hrel = (attr >> 3) & 3, (attr >> 8) & 3
    if attr & 1 or (attr >> 21) & 7 not in (2, 3) or (attr >> 5) & 7 or (attr >> 10) & 7: return None
    vo, ho = struct.unpack_from('<ii', ctl.p, 8); vo, ho = vo / 100, ho / 100
    if vrel == 2 and hrel in (2, 3):
        return '<div style="position:relative;height:0"><div style="position:absolute;left:%gpt;top:%gpt">%%s</div></div>' % (ho, vo)
    if vrel in (0, 1) and hrel in (0, 1):       # 종이 기준이면 본문 영역 원점으로 옮긴다(쪽 기준은 이미 본문 영역 기준)
        px = ho - (PAGEM[0] if hrel == 0 else 0); py = vo - (PAGEM[1] if vrel == 0 else 0)
        return '<div class="fo" style="--cx:%gpt;--cy:%gpt;--px:%gpt;--py:%gpt">%%s</div>' % (px, py, px + PAGEM[0], py + PAGEM[1])
    return None


def render_para(n, trim=(), body=False):
    ps = parashapes[struct.unpack_from('<H', n.p, 8)[0]]
    text = []; csr = []
    for ch in n.ch:
        if ch.tag == 67: text = para_text(ch.p)
        elif ch.tag == 68: csr = [struct.unpack_from('<II', ch.p, 8 * k) for k in range(len(ch.p) // 8)]
    ctrls = [ch for ch in n.ch if ch.tag == 71]
    ci = 0; inner = []; cur = None; buf = ''

    def csat(pos):
        r = csr[0][1]
        for a, bb in csr:
            if a <= pos: r = bb
        return r

    def flush():
        nonlocal buf
        if buf:
            cs = charshapes[cur]
            for lang, chunk in script_runs(buf):      # 글을 언어 칸(한글·영어·한자·기호…)별로 나눠 칸마다 글꼴·장평·자간·상대 크기를 준다
                # white-space:pre-wrap 은 WeasyPrint 가 줄바꿈 자리를 잘못 골라("1. " 만 한 줄에 남김) 쓰지 않고, 연속 공백은 '줄바꿈 가능한 공백 + &nbsp;'로 보존한다
                esc = re.sub(' {2,}', lambda m: ' ' + '&nbsp;' * (len(m.group()) - 1), html.escape(chunk)).replace('\n', '<br>')       # 탭 글자는 아래에서(오른쪽 맞춤 탭이면 한 줄 flex 로, 아니면 &emsp;)
                if not inner and esc.startswith(' '): esc = '&nbsp;' + esc[1:]          # 문단 맨 앞 공백은 일반 모드에서 사라지므로
                inner.append('<span style="%s">%s</span>' % (span_style(cs, lang, lang == 1), esc))
            buf = ''
    blocks = []; front = []; tac_sp = tac_mt = 0       # front: 글 앞/뒤에 떠 있어 자리를 안 차지하는 개체(문단 맨 위에 겹쳐 놓는다)
    brks = set(); single = False
    if STORED:
        segs_ = [x for x in n.ch if x.tag == 69]
        if segs_ and all(len(sg.p) >= 36 for sg in segs_):
            starts = [struct.unpack_from('<I', sg.p, 36 * k)[0] for sg in segs_ for k in range(len(sg.p) // 36)]
            if len(starts) == 1: single = True
            else: brks = {x for x in starts[1:]}
    n_tbl = sum(1 for _, v in text if isinstance(v, tuple) and v[1] == 'tbl ')        # 한 문단에 표가 여럿이면 나란히(글자처럼) 놓는다
    for pos, v in text:
        if pos in brks: flush(); inner.append(LB)
        if isinstance(v, tuple):
            while ci < len(ctrls) and ctrls[ci].p[:4][::-1].decode('latin1') != v[1]: ci += 1
            if ci < len(ctrls):
                ctl = ctrls[ci]; ci += 1
                if v[1] == 'tbl ':
                    flush(); t = render_table(ctl, inline=n_tbl > 1, pa=(ps['align'], ps['left'] / 200))
                    if n_tbl > 1: inner.append(t)       # 한 문단에 표가 여럿이면 글 사이 제자리에(사이의 공백·탭이 간격이 된다: 달력의 월 표)
                    elif float_obj(ctl): front.append(float_obj(ctl) % t)
                    else:
                        blocks.append(('inl', t))
                        if len(ctl.p) >= 36 and struct.unpack_from('<I', ctl.p, 4)[0] & 1:
                            if ps['lstype'] == 0 and ps['ls'] > 100:       # 글자처럼 취급 표: 한컴은 표 아래에 줄 간격만큼(N-1)×글자 크기를 더 둔다(저장된 줄 정보: 표 65pt + 간격 7.8pt). 공문 서식의 표 3개에서 25pt 가 모자랐다
                                tac_sp = (ps['ls'] / 100 - 1) * charshapes[csat(pos)]['size'] * 4 / 3
                            # 개체 바깥 여백 위·아래: 줄 높이 = 표 높이 + 위 + 아래(공문서양식 제목 표 34.97 + 2×2.83 = 저장된 줄 40.6). 위쪽은 padding, 아래쪽은 줄 간격 margin 에 합친다(margin 끼리는 겹쳐서 큰 값만 남는다)
                            mt_, mb_ = struct.unpack_from('<2H', ctl.p, 32); tac_mt = min(mt_, 3000) / 75; tac_sp += min(mb_, 3000) / 75
                elif v[1] == 'gso ':
                    flush(); g = render_gso(ctl)
                    if len(ctl.p) >= 8 and struct.unpack_from('<I', ctl.p, 4)[0] & 1: inner.append(g)      # 글자처럼 취급: 글 사이 제자리에(블록으로 뒤에 붙이면 로고가 글 아래로 내려간다)
                    elif not g: pass            # 그려지지 않는 도형(선·빈 도형)은 문단 줄을 지우지 않게 아무것도 안 붙인다(<p> 가 있어야 한컴처럼 줄 높이가 남는다)
                    elif float_obj(ctl): front.append(float_obj(ctl) % g)
                    else: blocks.append(('inl', g))
                elif v[1] in ('head', 'foot'):
                    paras = [x for x in ctl.ch if x.tag == 66] + [y for x in ctl.ch if x.tag == 72 for y in x.ch if y.tag == 66]
                    h = render_paras(paras)
                    if h and h not in HF[v[1]]: HF[v[1]].append(h)      # 홀·짝 쪽이 서로 다르면 둘 다, 같으면 한 번만
                    HFM[v[1]].append((CUR[0], struct.unpack_from('<I', ctl.p, 4)[0] & 3 if len(ctl.p) >= 8 else 0, h))
                elif v[1] == 'atno' and not MASTER[0] and len(ctl.p) >= 8 and struct.unpack_from('<I', ctl.p, 4)[0] & 0xF == 0:     # 자동 번호 중 '쪽 번호'. 바탕쪽 안은 뺀다: 쪽마다 반복되는 고정 상자에서 WeasyPrint 가 모든 쪽을 1 로 계산해 틀린 숫자가 찍힌다
                    flush(); inner.append('<span class="pgno" style="%s"></span>' % span_style(charshapes[csat(pos)]))
                elif v[1] == 'pgnp' and len(ctl.p) >= 14:       # 쪽 번호 위치(공식 표 147·148): 속성 4B(비트0~7 번호 모양, 비트8~11 위치), 사용자 기호·앞 장식·뒤 장식 WCHAR
                    a, fr, bk = struct.unpack_from('<IxxHH', ctl.p, 4); dash = struct.unpack_from('<H', ctl.p, 14)[0] if len(ctl.p) >= 16 else 0
                    # 앞·뒤 장식 문자가 모두 비면 한컴 기본 서식 "- 1 -"(마지막 칸의 줄표). form-002 한컴 PDF 로 확인
                    PGNP[0] = (a, chr(fr) if fr else (chr(dash) + ' ' if dash and not bk else ''), chr(bk) if bk else (' ' + chr(dash) if dash and not fr else ''))
                elif v[1] == 'form':
                    k = csat(pos)
                    if k != cur: flush(); cur = k
                    box = form_box(ctl)
                    if box: flush(); inner.append(box)
                    else: buf += form_text(ctl)
            continue
        k = csat(pos)
        if k != cur: flush(); cur = k
        buf += v
    flush()
    prefix = ''; hang = None
    nid = ps['numid'] if ps['head'] == 2 else OUTLINE[0]        # 번호(2)는 문단 모양이 가리키는 번호 모양, 개요(1)는 구역 정의가 정한 번호 모양
    if ps['head'] in (1, 2) and 0 < nid <= len(numberings) and text:
        key = (nid, ps['level']); NUMC[key] = NUMC.get(key, 0) + 1
        for k in list(NUMC):
            if k[0] == nid and k[1] > ps['level']: del NUMC[k]
        lv = numberings[nid - 1]
        prefix = re.sub(r'\^(\d)', lambda m: num_shape(NUMC.get((nid, int(m.group(1)) - 1), 1), lv[min(int(m.group(1)), 7) - 1]['shape']), lv[ps['level']]['fmt']) + ' '
        lvl = lv[ps['level']]
        if lvl['hang']:        # 자동 내어쓰기: 번호는 왼쪽 끝, 글(둘째 줄부터도)은 번호 너비 + 본문과의 거리만큼 안쪽. 거리는 글자 크기의 %(기본) 또는 값(HWPUNIT)
            hang = max(0, lvl['dist'] / 100 / max(charshapes[csat(0)]['size'], 1)) if lvl['dist_abs'] else max(0, lvl['dist'] / 100)
    num_span = '<span style="%s">%s</span>' % (span_style(charshapes[csat(0)]), html.escape(prefix.strip() if hang is not None else prefix)) if prefix else ''
    if prefix and hang is None: inner.insert(0, num_span)
    st = ['text-align:' + ALIGN.get(ps['align'], 'left')]
    if ps['bw']: st.append('word-break:break-all')      # 글자 단위 줄 나눔 문단(HWPX 경로의 breakNonLatinWord=BREAK_WORD 와 같은 규칙)
    ind = ps['indent'] / 2; left = ps['left'] / 2
    if ps['right'] > 0: st.append('padding-right:%.1fpx' % hu(ps['right'] / 2))       # 문단 오른쪽 여백(예전엔 안 읽어서 정답보다 줄이 늦게 꺾였다)
    if hang is not None:
        if left: st.append('padding-left:%.1fpx' % hu(left))
    elif ind < 0: st.append('padding-left:%.1fpx' % hu(left - ind)); st.append('text-indent:%.1fpx' % hu(ind))
    else:
        if left: st.append('padding-left:%.1fpx' % hu(left))
        if ind: st.append('text-indent:%.1fpx' % hu(ind))
    sp_top, sp_bot = hu(ps['top'] / 2), hu(ps['bottom'] / 2)       # 문단 간격은 앞 문단 아래 + 이 문단 위가 더해진다(한컴). margin 은 겹쳐 큰 쪽만 남으니 padding 으로 준다
    mt = mb = 0
    if trim and ps['lstype'] == 0 and ps['ls'] > 100 and csr:
        # 한컴은 줄 간격(%)을 줄 아래에만 붙이고 칸 맨 위 줄 앞·맨 아래 줄 뒤에는 안 붙인다(12pt 한 줄 칸 = 12pt + 여백). CSS line-height 는 위아래로 반씩 붙으니
        # 칸 안 첫·끝 문단은 반씩 되돌려 한컴과 같은 칸 높이·글 위치로 만든다.
        half = (ps['ls'] / 100 - 1) / 2 * charshapes[csat(0)]['size'] * 4 / 3
        if 'top' in trim: mt -= half
        if 'bottom' in trim: mb -= half
    if body and ps['lstype'] == 0 and ps['ls'] > 100 and csr:
        # 한컴은 줄 간격(%)을 줄 아래에만 붙이고 CSS 는 위·아래 반씩이라 본문 글이 (N-1)/2×글자 크기만큼 낮게 앉는다(표준 공문 양식 +2.8pt, 글꼴 시험 문서 4건 유사도 0.53→0.66).
        # 위로 반만큼 당기고(음수 margin-top) 아래에 그만큼 채워(margin-bottom, 앞 문단 margin 과 합쳐져 간격은 그대로) 흐름 높이를 유지한다. position:relative 로 올리면 PDF 글 순서가 뒤섞여 복사·검색이 어지럽다.
        half = (ps['ls'] / 100 - 1) / 2 * charshapes[csat(0)]['size'] * 4 / 3; mt -= half; mb += half
    bfd = borderfills[ps['bf'] - 1] if 0 < ps['bf'] <= len(borderfills) else None
    visible = lambda b: bool(b and ((b['borders'] and any(x[0] for x in b['borders'])) or b['grad'] or (b['fill'] is not None and b['fill'] & 0xFFFFFF != 0xFFFFFF)))
    if visible(bfd):        # 문단 테두리·배경(공식 표 43의 문단 모양 '테두리/배경 ID'): 좌우 여백과 위아래 간격은 테두리 바깥(margin), 테두리 간격은 안쪽(padding)
        st = [x.replace('padding-left:', 'margin-left:').replace('padding-right:', 'margin-right:') for x in st]
        if bfd['borders']: st += [border_css(side, b) for side, b in zip(('left', 'right', 'top', 'bottom'), bfd['borders'])]
        if bfd['grad']: st.append('background:linear-gradient(%ddeg,%s)' % ((180 - bfd['grad'][0]) % 360, ','.join(bfd['grad'][1])))
        elif bfd['fill'] is not None and bfd['fill'] & 0xFFFFFF != 0xFFFFFF: st.append('background:' + rgb(bfd['fill']))
        st.append('padding:%.1fpx %.1fpx %.1fpx %.1fpx' % (hu(ps['bsp'][2]), hu(ps['bsp'][1]), hu(ps['bsp'][3]), hu(ps['bsp'][0])))
        if sp_top + mt: st.append('margin-top:%.1fpx' % (sp_top + mt))
        if sp_bot + mb: st.append('margin-bottom:%.1fpx' % (sp_bot + mb))
    else:
        if sp_top: st.append('padding-top:%.1fpx' % sp_top)
        if sp_bot: st.append('padding-bottom:%.1fpx' % sp_bot)
        if mt: st.append('margin-top:%.1fpx' % mt)
        if mb: st.append('margin-bottom:%.1fpx' % mb)
    if n.p[11] & 4 or ps['pbreak']: st.append('break-before:page')       # 문단 머리의 '쪽 나누기' 표시, 또는 문단 모양의 '문단 앞에서 항상 쪽 나눔'
    if ps['widow']: st.append('orphans:2;widows:2')
    if ps['lstype'] == 0 and ps['ls']: st.append('line-height:%.2f' % (ps['ls'] / 100))      # 한컴의 줄 간격 N% = 글자 크기의 N/100 배(저장된 줄 정보로 확인: 10pt, 160% → 줄 간격 16pt)
    elif ps['lstype'] == 1 and ps['ls']: st.append('line-height:%gpt' % (ps['ls'] / 200))       # 고정값: 문단 여백처럼 저장값이 2배(HWPUNIT×2). 저장된 줄 정보로 확인: ls 4000 → 줄 간격 20pt, 3200 → 16pt
    if csr and charshapes[csat(0)]['face']: st.append(family(charshapes[csat(0)]['face']))
    if csr: st.append('font-size:%gpt' % charshapes[csat(0)]['size'])      # 문단 자체의 글자 크기. 없으면 기본 16px 기준으로 줄 높이가 부풀고, 글자 없는 빈 줄(3pt 같은 아주 작은 줄)이 커진다
    if inner and inner[-1].endswith('<br></span>'): inner[-1] = inner[-1][:-len('<br></span>')] + '<br>&nbsp;</span>'      # 문단 끝의 줄 바꿈: HTML 은 끝의 <br> 에 빈 줄을 안 만든다(한컴은 둘째 줄을 비워 둠 — 표준 공문 양식에서 줄 하나(17.6pt)가 사라졌다). &nbsp; 로 빈 줄을 만든다(영폭 공백은 PDF 글자에 보이지 않는 글자를 남겨 검색·복사를 어지럽힌다)
    if LB in inner and (hang is not None or any(chr(9) in x for x in inner)): inner = [x for x in inner if x != LB]       # 탭·내어쓰기 문단은 저장된 줄 바꿈을 쓰지 않는다
    tattr, stops = tabdefs[ps['tab']] if ps['tab'] < len(tabdefs) else (0, [])
    ti = [i for i, s in enumerate(inner) if '\t' in s]
    if len(ti) == 1 and inner[ti[0]].count('\t') == 1 and ((tattr & 2 and not stops) or (stops and stops[0][1] == 1)):
        # 탭이 한 번이고 그 자리가 오른쪽 맞춤이면(문단 오른쪽 끝 자동 탭, 또는 첫 명시 탭이 오른쪽 맞춤) 한 줄 flex: [앞글][채움선][뒷글]. 뒷글이 오른쪽 끝에 붙는다.
        i = ti[0]; sp_open = re.match(r'<span style="[^"]*">', inner[i]).group(); a, b = inner[i].split('\t')
        leader = ';border-bottom:1px dotted #000' if stops and stops[0][2] else ''
        body = '<span class="tl">%s%s</span></span><span class="tf" style="%s"></span><span class="tr">%s%s</span>' % (''.join(inner[:i]), a, leader.lstrip(';'), sp_open + b, ''.join(inner[i + 1:]))
        st.append('display:flex')
    elif LB in inner or (single and not blocks and inner):       # 저장된 줄마다 한 줄 상자: 줄 바꿈 금지(우리 글꼴 폭이 달라도 줄 수는 한컴과 같게), 마지막 줄 말고는 양쪽 맞춤이면 끝까지 늘림
        lines = [[]]
        for x in inner:
            if x == LB: lines.append([])
            else: lines[-1].append(x)
        just = 'text-align-last:justify;' if ps['align'] in (0, 4, 5) else ''
        body = ''.join('<span style="display:block;white-space:nowrap;%s">%s</span>' % ('' if k == len(lines) - 1 else just, ''.join(l) or '&nbsp;') for k, l in enumerate(lines))
    else:
        body = ''.join(inner).replace('\t', '&emsp;')
    if hang is not None:        # 자동 내어쓰기: [번호][글] 두 칸 flex — 글이 둘째 줄부터도 번호 뒤에 맞춰진다
        if 'display:flex' in st: body = num_span + body
        else:
            body = '<span style="flex:0 0 auto;margin-right:%gem">%s</span><span style="flex:1 1 0;min-width:0">%s</span>' % (hang, num_span, body); st.append('display:flex')
    out = ''.join(front)
    if body or not blocks:
        out += '<p style="%s">%s</p>' % (';'.join(st), body or '&nbsp;')
    for _, bl in blocks: out += bl
    if blocks and not (body or not blocks) and (sp_top or sp_bot or tac_sp or tac_mt):       # 표·그림만 있는 문단은 <p> 가 없어 문단 간격이 빠지니 상자로 감싼다. 표 아래 줄 간격은 margin 으로: 쪽 끝에서 margin 은 잘려 넘치지 않지만 padding 은 표 통째를 다음 쪽으로 민다
        out = '<div style="padding:%.1fpx 0 %.1fpx%s">%s</div>' % (sp_top + tac_mt, sp_bot, ';margin-bottom:%.1fpx' % tac_sp if tac_sp else '', out)
    if n.p[11] & 4 and not (body or not blocks): out = '<div style="break-before:page"></div>' + out      # 표만 있는 문단은 <p> 가 없어 쪽 나누기를 따로 둔다
    return out


def render_paras(nodes, trim=False):
    ps = [n for n in nodes if n.tag == 66]
    return '\n'.join(render_para(n, tuple(k for k, on in (('top', i == 0), ('bottom', i == len(ps) - 1)) if on) if trim else ()) for i, n in enumerate(ps))


def text_len(paras):
    return sum(len(v.strip()) for n in paras for ch in n.ch if ch.tag == 67 for _, v in para_text(ch.p) if isinstance(v, str))


BORDER_MM = [0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0]      # 굵기 번호 -> mm
BORDER_STYLE = {2: 'dashed', 3: 'dotted', 4: 'dashed', 5: 'dashed', 6: 'dashed', 7: 'dotted', 8: 'double', 9: 'double', 10: 'double', 11: 'double', 13: 'double'}   # 종류 번호 -> CSS (1=실선, 0=없음)


def border_css(side, b):
    """side: left|right|top|bottom, b: (종류, 굵기 번호, 색). 종류 0 은 선 없음."""
    ty, wd, color = b
    if ty == 0: return f'border-{side}:none'
    mm = BORDER_MM[min(wd, 15)]
    style = BORDER_STYLE.get(ty, 'solid')
    if style == 'double': mm = max(mm, 0.5)         # 얇으면 이중선이 한 줄로 보여서
    return f'border-{side}:{mm:g}mm {style} {color}'


SPLIT_ON = (os.environ.get('SPLIT_ROWS') or 'on') == 'on'      # 켬(SPLIT_ROWS=off 로 끔). 임계값 300pt 로 사용자 8건 0.552 유지, 공개 108건 쪽 70→72·유사도 0.427→0.435(인수인계 문서 2026-10-12). 80pt 였을 땐 사용자 근무계획서가 후퇴했다
SPLIT_MIN = float(os.environ.get('SPLIT_MIN', 300))      # pt. 이 높이 이상인 행만 줄 단위로 나뉘게 한다(작은 행은 어차피 쪽 경계에 안 걸린다)
SPLIT_FILL = float(os.environ.get('SPLIT_FILL', 0.9))    # 행의 어느 칸이든 글(저장된 줄 정보)이 칸 안쪽 높이의 이 비율 이상(SPLIT_OVER 배 이하)이면 '찬 행'
SPLIT_OVER = float(os.environ.get('SPLIT_OVER', 1.1))


def split_plan(cells):
    """셀 단위로 나뉘는 표(HWP 표 속성 비트 0~1 = 2, HWPX pageBreak=CELL)의 '찬' 높은 행이면 True: 이 행 모든 칸의 height 를 뺀다.
    WeasyPrint 는 td·tr 에 height 가 있으면 행 전체를 다음 쪽으로 밀고, 없으면 줄 단위로 나눈다(시험: 22줄 행 15/7줄 대 0/22줄). 한컴은 셀 단위 나눔 표를 줄 단위로 나눠 이으니
    글이 칸을 채운 행(서술란)은 height 없이도 행 높이가 칸 높이 근처가 되어 안전하다. 글이 못 채운 행(빈 답안 칸·서식)은 height 가 행 높이를 지키므로 그대로 둔다.
    시도했다 버린 것: ① div min-height 로 높이 지키기 — WeasyPrint 가 쪽을 넘어간 뒷조각에 min-height 를 통째로 다시 적용해 행이 부푼다(pr-1674 행 9 뒷조각 141pt → 355pt).
    ② 모자란 높이를 padding 으로 채우기 — 저장된 줄 정보가 낡은 파일(form-002)은 글 높이를 작게 적어 padding 이 과해져 10쪽이 15쪽이 됐다.
    cells: 한 행의 [(칸 높이 pt, 위+아래 안쪽 여백 pt, 걸친 행 수, 저장된 줄 정보로 잰 글 높이 pt)]. 걸친 행이 있는 행은 건드리지 않는다. PDF 길(STORED)에서만 부른다."""
    if not cells or any(c[2] != 1 for c in cells) or max(c[0] for c in cells) < SPLIT_MIN: return False
    return any(SPLIT_FILL * (h - pad) <= ct <= SPLIT_OVER * (h - pad) and h > pad for h, pad, _, ct in cells)      # 칸 높이는 한컴이 저장한 실제 행 높이라 글이 그보다 훨씬 크면(근무계획서 287pt 칸에 475pt) 줄 정보가 떠 있는 개체·중첩 표를 센 것이니 믿지 않는다


KEEP_ROWS = os.environ.get('KEEP_ROWS') or 'span,first'      # 'span' 걸친 칸 묶음 붙이기 · 'first' 낮은 표 첫 줄 붙이기
KEEP_FIRST = float(os.environ.get('KEEP_FIRST', 30))      # pt. 이 높이 이하인 첫 줄만 다음 줄에 붙인다
KEEP_MAX = float(os.environ.get('KEEP_MAX', 150))      # pt. 이보다 큰 묶음은 한컴도 가른다고 본다(큰 묶음이 많은 문서에서 쪽이 늘었다)


def keep_rows(spans, first, first_h=0):
    """쪽 끝에서 바로 다음 줄과 갈라지면 안 되는 줄 번호 집합. spans: [(줄 번호, 걸친 줄 수, 걸친 칸 높이 pt)].
    한컴은 아래 줄로 걸친 칸(rowspan)이 든 줄 묶음을 쪽 경계에서 가르지 않고, 표의 첫 줄만 쪽 아래에 홀로 남기지 않는다고 본다(공고문 7쪽 '제출 서류' 표: 남은 105pt 에
    첫 줄 22pt + 걸친 칸 묶음 139pt 가 안 들어가자 표 전체를 8쪽 맨 위로 보냄; 우리는 첫 줄 + 묶음의 윗줄만 7쪽에 두고 가름). WeasyPrint 는 `tr{break-after:avoid}` 를 지킨다(시험)."""
    keep = set()
    if 'span' in KEEP_ROWS:
        for r, rs, h in spans:
            if h <= KEEP_MAX: keep.update(range(r, r + rs - 1))
    if 'first' in KEEP_ROWS and first_h <= KEEP_FIRST: keep.add(first)      # 제목처럼 낮은 첫 줄만(높은 첫 줄은 한컴도 쪽 아래에서 가른다: 'first' 를 가리지 않고 켜면 사용자 회의록이 0.543→0.155)
    return keep


def head_rows(nrow, cells, repeat):
    """표 맨 위에서 '제목 셀'(HWP 칸 속성 비트 18, HWPX tc header=1)이 든 줄 수 — 표 속성의 '제목 줄 자동 반복'(HWP 비트 2, HWPX repeatHeader)이 켜졌을 때만. 한컴은 표가 쪽을 넘으면 이 줄들을
    다음 쪽 맨 위에 되풀이해 그린다(pr-1674 한컴 19쪽). `<thead>` 로 내면 WeasyPrint 가 쪽마다 반복한다. 제목 줄 밖으로 걸친 칸(rowspan)이 있거나 표가 이 줄뿐이면 0.
    cells: dict(row, rs, hd) 목록. 두 변환기가 같은 규칙을 쓴다(공개 코퍼스에서 제목 셀은 거의 0행, 가끔 0~1행; repeatHeader=1 은 표 대부분의 기본값이라 제목 셀이 있어야 뜻이 있다)."""
    if not repeat: return 0
    n = 0
    while n < nrow and any(x['hd'] for x in cells if x['row'] == n): n += 1
    return n if 0 < n < nrow and all(x['row'] + x['rs'] <= n for x in cells if x['row'] < n) else 0


def text_bottom(paras):
    """칸 안 문단들의 저장된 줄 정보(PARA_LINE_SEG: 36B 줄 기록 = 글자 위치·세로 위치 y·줄 높이…)로 잰 글 높이 pt = 마지막 줄의 y + 높이. 줄 정보가 없으면 0."""
    bot = 0
    for p in paras:
        segs = [x for x in p.ch if x.tag == 69 and len(x.p) >= 36]
        if segs:
            last = segs[-1]; y, h = struct.unpack_from('<ii', last.p, len(last.p) // 36 * 36 - 32)
            bot = max(bot, (y + h) / 100)
    return bot


def render_table(ctl, inline=False, pa=None):
    """표 크기·칸 폭/높이·안쪽 여백·칸별 테두리를 문서에 저장된 값 그대로 쓴다. inline=True 면 같은 문단의 다른 표와 나란히(글자처럼) 놓는다."""
    tbl = next(ch for ch in ctl.ch if ch.tag == 77)
    rows, cols = struct.unpack_from('<HH', tbl.p, 4)
    cells = []; kids = ctl.ch
    i77 = next(i for i, ch in enumerate(kids) if ch.tag == 77)
    tmg = struct.unpack_from('<4H', tbl.p, 10) if len(tbl.p) >= 18 else None      # 표 기본 안쪽 여백 왼·오·위·아래
    caps = []                                       # 캡션(표 제목): TABLE 레코드보다 앞에 오는 LIST_HEADER. 칸이 아니다(예전엔 칸으로 읽어 첫 줄이 깨졌다)
    for idx, ch in enumerate(kids):
        if ch.tag == 72 and idx < i77:
            j = idx + 1
            while j < len(kids) and kids[j].tag == 66: caps.append(kids[j]); j += 1
            caps += [x for x in ch.ch if x.tag == 66]
            cap_below = len(ch.p) >= 12 and struct.unpack_from('<I', ch.p, 8)[0] & 3 == 3       # 방향: 0 왼 1 오른 2 위 3 아래
        elif ch.tag == 72:
            col, row, cs, rs, w, h = struct.unpack_from('<HHHHII', ch.p, 8)
            bf = struct.unpack_from('<H', ch.p, 32)[0] if len(ch.p) >= 34 else 0      # 옛 형식의 칸 레코드는 더 짧다(배경 정보 없음 → 0)
            mg = struct.unpack_from('<4H', ch.p, 24) if len(ch.p) >= 32 else None      # 안쪽 여백 왼·오·위·아래(HWPUNIT)
            if mg and any(v >= 0x8000 for v in mg): mg = tmg        # 칸 여백이 0xFFFF 같은 '지정 안 함' 값이면(655pt 여백으로 칸이 수십 쪽으로 불었다: img-start-001) 표의 기본 안쪽 여백
            vflag, = struct.unpack_from('<I', ch.p, 4)
            paras = []; j = idx + 1
            while j < len(kids) and kids[j].tag == 66: paras.append(kids[j]); j += 1
            paras += [x for x in ch.ch if x.tag == 66]
            cells.append(dict(row=row, col=col, cs=cs, rs=rs, w=w, h=h, mg=mg, bf=bf, valign=(vflag >> 5) & 3, hd=vflag >> 18 & 1, paras=paras))      # 세로 정렬은 속성의 비트 5~6(0 위, 1 가운데, 2 아래). 예전 코드는 비트 21~22 를 읽어 모든 칸이 '위'로 나왔다(hwp-cli 와 18칸 대조)
    x = {0: 0}; changed = True                      # 칸 주소(열, 걸친 열 수)와 폭에서 열 경계를 풀어낸다
    while changed:
        changed = False
        for cl in cells:
            a, b = cl['col'], cl['col'] + cl['cs']
            if a in x and b not in x: x[b] = x[a] + cl['w']; changed = True
            elif b in x and a not in x: x[a] = x[b] - cl['w']; changed = True
    for i in range(cols + 1):
        if i not in x: x[i] = x[i - 1] if i else 0
    colw = [max(x[i + 1] - x[i], 0) for i in range(cols)]
    st = ['border-collapse:collapse', 'table-layout:fixed', 'width:%gpt' % (sum(colw) / 100)]
    if inline: st += ['display:inline-table', 'vertical-align:top']
    elif len(ctl.p) >= 16:
        # 글자처럼 취급이 아닌 '자리 차지' 표(본문 배치 1)는 문단(세로)·단/문단(가로) 기준 오프셋만큼 떨어져 놓인다(rhwp 렌더 트리와 대조: 표 x = 본문 x + 가로 오프셋, 표준 공문 양식 7.95pt 일치).
        # 가운데·오른쪽 정렬(비트 5~7, 10~12)이면 기준 폭이 필요하니 건너뛴다. 오른쪽으로 넘쳐도 한컴처럼 그대로 둔다.
        attr, = struct.unpack_from('<I', ctl.p, 4); vo, ho = struct.unpack_from('<ii', ctl.p, 8)
        if not attr & 1 and (attr >> 21) & 7 == 1 and not (attr >> 5) & 7 and not (attr >> 10) & 7 and (attr >> 3) & 3 == 2 and (attr >> 8) & 3 in (2, 3):
            if ho > 0: st.append('margin-left:%gpt' % (ho / 100))
            if vo > 0: st.append('margin-top:%gpt' % (vo / 100))
        elif attr & 1 and pa and len(ctl.p) >= 36:
            # 글자처럼 취급 표는 그 문단의 정렬을 따른다: 가운데면 가운데, 오른쪽이면 오른쪽 끝(개체 바깥 여백만큼 안쪽), 왼쪽이면 문단 왼쪽 여백 + 바깥 여백. rhwp 렌더 트리와 대조(공문서양식: 오른쪽 정렬 표 오른쪽 끝 = 본문 오른쪽 − 2.83pt)
            ml, mr = struct.unpack_from('<2H', ctl.p, 28)
            al, lm = pa
            if al == 3: st.append('margin-left:auto;margin-right:auto')
            elif al == 2: st.append('margin-left:auto;margin-right:%gpt' % (mr / 100))
            elif lm or ml: st.append('margin-left:%gpt' % (lm + ml / 100))
    out = ['<table class="hwp-table" style="%s"><colgroup>%s</colgroup>' % (';'.join(st), ''.join('<col style="width:%gpt">' % (w / 100) for w in colw))]
    cellsplit = STORED and SPLIT_ON and len(tbl.p) >= 4 and struct.unpack_from('<I', tbl.p, 0)[0] & 3 == 2        # 표 속성 비트 0~1: 0 나누지 않음·1 행 단위로만·2 셀 단위로 나눔(hwp-cli 가 쓴 HWPX pageBreak NONE/TABLE/CELL 과 대조; 공식 문서 표 75 의 '2 나누지 않음'은 오타)
    nh = head_rows(rows, cells, len(tbl.p) >= 4 and struct.unpack_from('<I', tbl.p, 0)[0] >> 2 & 1)
    keep = keep_rows(((x['row'], x['rs'], x['h'] / 100) for x in cells), 0, max((x['h'] for x in cells if x['row'] == 0), default=0) / 100)
    if nh: out.append('<thead>')
    for r in range(rows):
        if nh and r == nh: out.append('</thead><tbody>')
        out.append('<tr style="break-after:avoid">' if r in keep else '<tr>')
        rc = [x for x in cells if x['row'] == r]
        plan = cellsplit and split_plan([(x['h'] / 100, sum((x['mg'] or (510, 510, 141, 141))[2:]) / 100, x['rs'], text_bottom(x['paras'])) for x in rc])
        for cell in rc:
            # 200pt 넘는 큰 칸에 글이 가득하면(높이 1pt 당 1자 이상) 높이를 글이 정하니 height 를 뺀다. 지정하면 WeasyPrint 가 쪽 경계에서 나뉜 앞부분도 그 높이로 쳐서 칸 전체를 다음 쪽으로 민다(한컴은 줄 단위로 나눠 이음).
            # 셀 단위로 나뉘는 표의 '찬' 높은 행(split_plan)도 height 를 뺀다.
            st = [] if plan or cell['h'] >= 20000 and text_len(cell['paras']) >= cell['h'] / 100 else ['height:%gpt' % (cell['h'] / 100)]
            ml, mr, mt, mb = cell['mg'] or (510, 510, 141, 141)       # 한컴 기본 여백
            st.append('padding:%gpt %gpt %gpt %gpt' % (mt / 100, mr / 100, mb / 100, ml / 100))
            bfd = borderfills[cell['bf'] - 1] if 0 < cell['bf'] <= len(borderfills) else None
            if bfd and bfd['borders']: st += [border_css(side, b) for side, b in zip(('left', 'right', 'top', 'bottom'), bfd['borders'])]
            else: st.append('border:none')
            if bfd and bfd['grad']: st.append('background:linear-gradient(%ddeg,%s)' % ((180 - bfd['grad'][0]) % 360, ','.join(bfd['grad'][1])))      # HWP 각도 0 = 위→아래, 90 = 왼→오른쪽(정답 PDF 의 띠와 대조)
            elif bfd and bfd['fill'] is not None and bfd['fill'] & 0xFFFFFF != 0xFFFFFF: st.append('background:' + rgb(bfd['fill']))
            st.append('vertical-align:' + ['top', 'middle', 'bottom'][min(cell['valign'], 2)])
            span = (' colspan="%d"' % cell['cs'] if cell['cs'] > 1 else '') + (' rowspan="%d"' % cell['rs'] if cell['rs'] > 1 else '')
            out.append('<td%s style="%s">%s</td>' % (span, ';'.join(st), render_paras(cell['paras'], trim=True)))
        out.append('</tr>')
    if nh: out.append('</tbody>')
    out.append('</table>')
    if caps:
        cap = render_paras(caps)
        return ''.join(out) + cap if cap_below else cap + ''.join(out)
    return ''.join(out)


def find(n, tag):
    if n.tag == tag: return n
    for ch in n.ch:
        r = find(ch, tag)
        if r: return r


def cold_of(node):
    """문단에 든 단 정의(마지막 것) -> (단 수, 단 사이 간격 pt, ';column-rule:…' 구분선 CSS). 없으면 None. 단 폭은 모두 같다고 본다."""
    r = None
    for ch in node.ch:
        if ch.tag == 71 and ch.p[:4][::-1] == b'cold' and len(ch.p) >= 8:
            attr, gap = struct.unpack_from('<HH', ch.p, 4); rule = ''
            if len(ch.p) >= 16 and attr >> 12 & 1 and ch.p[10]:          # 같은 폭이면 속성2(2B) 다음에 구분선 종류·굵기·색
                rule = ';column-rule:%gmm %s #%02x%02x%02x' % (BORDER_MM[min(ch.p[11], 15)], BORDER_STYLE.get(ch.p[10], 'solid'), ch.p[12], ch.p[13], ch.p[14])
            r = (max(1, (attr >> 2) & 0xFF), gap / 100, rule)
    return r


def master_layer(sd, pw, ph, ml, mt, mr, mb):
    """쪽마다 깔리는 층: 쪽 테두리(구역 정의의 PAGE_BORDER_FILL, 첫 번째 = 양쪽)와 바탕쪽(LIST_HEADER 다음 문단들)의 떠 있는 개체. 좌표는 pt(종이 기준)."""
    out = ''
    pbf = next((c for c in sd.ch if c.tag == 75 and len(c.p) >= 14), None)
    if pbf is not None:
        attr, sl, sr, st_, sb, bid = struct.unpack_from('<IHHHHH', pbf.p, 0)
        bfd = borderfills[bid - 1] if 0 < bid <= len(borderfills) else None
        if bfd and bfd['borders'] and any(b[0] for b in bfd['borders']):
            sl, sr, st_, sb = (v / 100 for v in (sl, sr, st_, sb))
            if attr & 1: x0, y0, x1, y1 = sl, st_, pw - sr, ph - sb            # 종이 기준: 종이 가장자리에서 안쪽으로
            else: x0, y0, x1, y1 = ml - sl, mt - st_, pw - mr + sr, ph - mb + sb      # 본문 기준: 본문 가장자리에서 바깥쪽으로
            css = ';'.join(border_css(side, b) for side, b in zip(('left', 'right', 'top', 'bottom'), bfd['borders']))
            out += '<div class="%s" style="--px:%gpt;--py:%gpt;--cx:%gpt;--cy:%gpt;width:%gpt;height:%gpt;box-sizing:border-box;%s"></div>' % ('mo mm' if x0 < ml or y0 < mt else 'mo', x0, y0, x0 - ml, y0 - mt, x1 - x0, y1 - y0, css)
    i = next((k for k, c in enumerate(sd.ch) if c.tag == 72), None)
    if i is not None:
        paras = []
        for c in sd.ch[i + 1:]:
            if c.tag == 72: break
            if c.tag == 66: paras.append(c)
        MASTER[0] = (ml, mt)
        try: out += render_paras(paras)
        finally: MASTER[0] = None
    return '<div class="hwp-master" style="height:0;overflow:visible">%s</div>\n' % out if out else ''


def find_ctrl(n, cid):
    if n.tag == 71 and n.p[:4][::-1].decode('latin1') == cid: return n
    for ch in n.ch:
        r = find_ctrl(ch, cid)
        if r: return r


def shape_box_css(shape):
    """도형(SHAPE_COMPONENT)의 테두리·채우기 -> CSS. 렌더링 행렬(개수 WORD@50, 행렬 (1+2n)개 × 48B)이 끝난 자리부터 선(색 4B·굵기 4B·속성 4B·바깥선 1B), 채움(종류 4B …)이 이어진다
    (request.hwp 글상자: 굵기 33, 색 검정 — 한컴 렌더와 대조). 선 종류 0·1 은 실선, 그 밖은 점선 계열로 본다."""
    p = shape.p
    if len(p) < 52: return []
    off = 52 + 48 * (1 + 2 * struct.unpack_from('<H', p, 50)[0])
    css = []
    if len(p) >= off + 12:
        lw = struct.unpack_from('<i', p, off + 4)[0]; kind = struct.unpack_from('<I', p, off + 8)[0] & 0x3F
        if lw > 0 and kind:        # 선 종류 0 은 '선 없음'(색·굵기 값이 남아 있어도 안 그린다. shortcut 바탕쪽 글상자). 1 실선, 그 밖은 BORDER_STYLE 처럼
            css.append('border:%gpt %s %s' % (max(lw / 100, 0.5), BORDER_STYLE.get(kind, 'solid'), rgb(struct.unpack_from('<I', p, off)[0])))
    if len(p) >= off + 21 and struct.unpack_from('<I', p, off + 13)[0] & 1:
        fc = struct.unpack_from('<I', p, off + 17)[0]
        if fc & 0xFFFFFF != 0xFFFFFF and fc != 0xFFFFFFFF: css.append('background:' + rgb(fc))
    return css


def render_gso(ctl):
    """그리기 개체: 글상자·도형 안에 글이 있으면 그 문단들을, 아니면 그림을 낸다. 크기는 개체 머리(CTRL_HEADER)에 저장된 폭·높이.
    ponytail: 쪽·문단 기준으로 떠 있는 개체도 제자리(앵커 문단 다음)에 흘려 놓는다 — 위치(절대 좌표)와 도형 테두리는 재현 안 함."""
    w, h = struct.unpack_from('<II', ctl.p, 16) if len(ctl.p) >= 24 else (0, 0)
    inline = len(ctl.p) >= 8 and struct.unpack_from('<I', ctl.p, 4)[0] & 1        # 글자처럼 취급
    shape = next((x for x in ctl.ch if x.tag == 76), None)
    paras = [x for x in (shape.ch if shape else []) if x.tag == 66]
    if paras:
        st = ['display:inline-block;vertical-align:top' if inline else 'display:block', 'box-sizing:border-box'] + (['width:%gpt' % (w / 100), 'min-height:%gpt' % (h / 100)] if w and h else [])
        st += shape_box_css(shape)
        r = '<div style="%s">%s</div>' % (';'.join(st), render_paras(paras))
    else:
        pic = find(ctl, 85)
        if not pic: return ''
        bid, = struct.unpack_from('<H', pic.p, 71)
        size = ' style="width:%gpt;height:%gpt"' % (w / 100, h / 100) if w and h else ''
        uri = bindata_uri(bid)
        if not uri: return ''
        r = '<img src="%s" alt="첨부 이미지 %d"%s>' % (uri, bid, size)
        if not inline: r = '<figure>%s</figure>' % r
    if MASTER[0] and not inline:       # 바탕쪽의 떠 있는 개체: 모든 쪽의 정해진 자리에(인쇄는 position:fixed, 화면은 absolute). 좌표는 종이 기준 pt, 쪽 기준이면 여백을 더한다
        pl, pt = MASTER[0]; attr, vo, ho = struct.unpack_from('<Iii', ctl.p, 4)
        px = ho / 100 + (pl if (attr >> 8) & 3 == 1 else 0); py = vo / 100 + (pt if (attr >> 3) & 3 == 1 else 0)
        r = '<div class="%s" style="--px:%gpt;--py:%gpt;--cx:%gpt;--cy:%gpt">%s</div>' % ('mo mm' if px < pl or py < pt else 'mo', px, py, px - pl, py - pt, r)
    return r


def build_section(root, idx):
    """한 구역(Section 파일 하나)을 (본문 HTML, 쪽 CSS, 화면용 CSS, 제목 글)로. idx 0 은 이름 없는 기본 @page, 1부터는 이름 있는 쪽(@page s1, 본문 <div style="page:s1">)이라
    구역마다 용지·여백·머리말·꼬리말·쪽 번호가 따로 선다. 구역 나누기는 새 쪽에서 시작한다(한컴과 같음)."""
    sd = find_ctrl(root, 'secd')
    if sd and len(sd.p) >= 20: OUTLINE[0] = struct.unpack_from('<H', sd.p, 18)[0] or 1       # 구역 정의의 '번호 문단 모양 ID'
    n_head, n_foot = len(HF['head']), len(HF['foot'])
    pd0 = find(root, 73)
    if pd0 and len(pd0.p) >= 40:
        _, _, pl0, _, pt0, _, ph0, _, pg0 = struct.unpack_from('<9I', pd0.p, 0); PAGEM[0], PAGEM[1] = (pl0 + pg0) / 100, (pt0 + ph0) / 100      # 본문 왼쪽(왼 여백+제본)·위쪽(위 여백+머리말)
    nodes = [n for n in root.ch if n.tag == 66]
    m0 = {k: len(HFM[k]) for k in HFM}
    blocks = []
    for ci, n in enumerate(nodes):
        CUR[0] = ci; blocks.append(render_para(n, body=True))
    if STORED_P:      # 한컴이 저장한 줄 위치가 앞 문단보다 위로 되돌아가면(또는 '쪽의 첫 줄' 표시) 새 쪽에서 시작
        prev = None
        for i, n in enumerate(nodes):
            sg = next((x for x in n.ch if x.tag == 69), None)
            if not (sg and len(sg.p) >= 36): continue
            vp, tg = struct.unpack_from('<i', sg.p, 4)[0], struct.unpack_from('<I', sg.p, 32)[0]
            if i and prev is not None and (vp < prev or tg & 1) and 'break-before:page' not in blocks[i]: blocks[i] = '<div style="break-before:page"></div>' + blocks[i]
            prev = vp
    # 쪽 나누기 바로 앞이나 문서 맨 끝의 빈 문단은 눈에 안 보이는데, 쪽 끝에 아슬아슬하게 걸리면 빈 쪽을 하나 더 만든다
    empty = lambda b: re.fullmatch(r'<p style="[^"]*">&nbsp;</p>', b) is not None
    keep = [not (empty(b) and i + 1 < len(nodes) and nodes[i + 1].p[11] & 4) for i, b in enumerate(blocks)]
    i = len(blocks) - 1
    while i > 0 and empty(blocks[i]): keep[i] = False; i -= 1
    groups = []         # 단 정의(다단)가 같은 문단끼리 묶는다. 문단에 든 단 정의는 그 문단부터 적용된다
    cols = (1, 0, '')
    for nd, b, k in zip(nodes, blocks, keep):
        cols = cold_of(nd) or cols
        if not k: continue
        if groups and groups[-1][0] == cols: groups[-1][1].append(b)
        else: groups.append((cols, [b]))
    body = '\n'.join(('<div style="column-count:%d;column-gap:%gpt%s">%s</div>' % (c[0], c[1], c[2], '\n'.join(bs))) if c[0] > 1 else '\n'.join(bs) for c, bs in groups)
    first = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', body.split('</p>')[0]))).strip()
    # 머리말·꼬리말: 내용(글·그림)이 있는 첫 번째 것만. 본문 흐름에 넣으면 한컴과 달리 본문이 밀려 쪽이 늘어나서(한컴은 위쪽 여백 안의 머리말 영역에 그림),
    # 아래 @page 의 쪽 여백 상자(WeasyPrint running 요소)로 보내 쪽마다 반복한다. 브라우저는 running 을 몰라 본문 맨 앞/끝에 한 번 보인다.
    # 이 구역에서 새로 나온 것이 없으면 앞 구역 것을 이어 쓴다(한컴: 바꾸기 전까지 이어짐).
    vis = lambda h: '<img' in h or bool(re.sub(r'<[^>]+>|&nbsp;|\s', '', h))
    sfx = str(idx) if idx else ''
    def eff(kind, applies):
        # 구역 첫 문단에 걸린 정의는 마지막 것이 이긴다(공문서양식: 로고가 든 머리말 뒤에 빈 머리말이 또 있어 한컴 1쪽엔 로고가 없다). 빈 것이면 '없음'(앞 구역 것도 안 이음).
        # 첫 문단 밖에서 정의된 것은 쪽마다 바뀌는 걸 못 따르니 내용 있는 첫 것을 쓴다. 못 찾으면 None(앞 구역에서 이음)
        ms = HFM[kind][m0[kind]:]; first = [m for m in ms if m[0] == 0 and m[1] in applies]
        if first: return first[-1][2] if vis(first[-1][2]) else ''
        return next((m[2] for m in ms if m[1] in applies and vis(m[2])), None)
    pick = lambda kind, k, applies: (lambda v: LAST_HF[kind][k] if v is None else (v or None))(eff(kind, applies))
    hd_o, hd_e = pick('head', 0, (0, 2)), pick('head', 1, (0, 1))        # 홀수 쪽 / 짝수 쪽 (한컴의 첫 쪽은 홀수)
    ft_o, ft_e = pick('foot', 0, (0, 2)), pick('foot', 1, (0, 1))
    LAST_HF['head'], LAST_HF['foot'] = (hd_o, hd_e), (ft_o, ft_e)
    hd, ft = hd_o or hd_e, ft_o or ft_e
    same_h, same_f = hd_o == hd_e, ft_o == ft_e
    hdivs = ('<div class="hwp-header%s">%s</div>\n' % (sfx, hd) if hd else '') if same_h else ''.join('<div class="hwp-header%s%s">%s</div>\n' % (sfx, t, h) for t, h in (('o', hd_o), ('e', hd_e)) if h)
    fdivs = ('\n<div class="hwp-footer%s">%s</div>' % (sfx, ft) if ft else '') if same_f else ''.join('\n<div class="hwp-footer%s%s">%s</div>' % (sfx, t, f) for t, f in (('o', ft_o), ('e', ft_e)) if f)
    body = hdivs + body + fdivs
    pd = find(root, 73)         # PAGE_DEF: 종이 크기·여백(hwp-cli 가 읽은 값과 일치함을 확인). 본문은 (위 여백 + 머리말 높이)에서 시작한다
    if not (pd and len(pd.p) >= 40): return body, '', '', first
    name = ' s%d' % idx if idx else ''
    pw, ph, pl, pr_, pt_, pb, phd, pft, pgt = struct.unpack_from('<9I', pd.p, 0)
    if struct.unpack_from('<I', pd.p, 36)[0] & 1: pw, ph = ph, pw        # 속성 비트0 = 용지 방향 '넓게'(가로): 저장된 폭·높이는 세로 기준이라 서로 바꾼다(shortcut·KTX 로 확인)
    PT = lambda v: '%gpt' % (v / 100)
    mg = f'{PT(pt_ + phd)} {PT(pr_)} {PT(pb + pft)} {PT(pl + pgt)}'
    if sd and not idx:      # ponytail: 쪽 테두리·바탕쪽 떠 있는 개체는 첫 구역 것만(position:fixed 라 모든 쪽에 깔린다). 구역마다 다르면 둘째부터는 안 그린다
        body = master_layer(sd, pw / 100, ph / 100, (pl + pgt) / 100, (pt_ + phd) / 100, pr_ / 100, pb / 100) + body
    tw = PT(pw - pl - pr_ - pgt)
    hbox = lambda nm, h, f: (f'@top-left{{content:element(hwphead{nm});width:{tw};vertical-align:top;padding-top:{PT(pt_)}}}' if h else '') + (f'@bottom-left{{content:element(hwpfoot{nm});width:{tw};vertical-align:top}}' if f else '')
    mbox = hbox(sfx, hd if same_h else None, ft if same_f else None)
    parity = ''
    if not (same_h and same_f):       # 홀수 쪽(오른쪽 쪽)·짝수 쪽(왼쪽 쪽)에서 머리말·꼬리말이 다르면 쪽 종류별로
        parity = ''.join('@page%s:%s{%s}\n' % (name, side, hbox(sfx + t, None if same_h else h, None if same_f else f)) for side, t, h, f in (('right', 'o', hd_o, ft_o), ('left', 'e', hd_e, ft_e)))
    side_css = ''; pn = PGNP[0]
    if pn and (pn[0] >> 8) & 0xF:         # 쪽 번호: 쪽 여백 상자의 counter(page) 로 쪽마다 찍는다
        a, fr, bk = pn; where = (a >> 8) & 0xF; cnt = {2: 'upper-roman', 3: 'lower-roman', 4: 'upper-alpha', 5: 'lower-alpha'}.get(a & 0xFF, 'decimal')
        clean = lambda ch: ''.join(c for c in ch if c not in ('"', chr(92)))
        content = 'content:"%s" counter(page,%s) "%s";font-size:10pt' % (clean(fr), cnt, clean(bk))
        names = {1: 'top-left', 2: 'top-center', 3: 'top-right', 4: 'bottom-left', 5: 'bottom-center', 6: 'bottom-right'}
        if where in names and not (names[where] == 'top-left' and hd) and not (names[where] == 'bottom-left' and ft): mbox += '@%s{%s}' % (names[where], content)
        elif where > 6:       # 바깥쪽(7·8)·안쪽(9·10): 홀수 쪽(오른쪽 쪽)과 짝수 쪽(왼쪽 쪽)이 반대편에
            edge = 'top' if where in (7, 9) else 'bottom'; outside = where in (7, 8)
            side_css = '@page%s:right{@%s-%s{%s}}@page%s:left{@%s-%s{%s}}\n' % (name, edge, 'right' if outside else 'left', content, name, edge, 'left' if outside else 'right', content)
    run = ''.join(f'.hwp-header{sfx}{t}{{position:running(hwphead{sfx}{t})}}\n' for t, h in ((('', hd),) if same_h else (('o', hd_o), ('e', hd_e))) if h)
    run += ''.join(f'.hwp-footer{sfx}{t}{{position:running(hwpfoot{sfx}{t})}}\n' for t, f in ((('', ft),) if same_f else (('o', ft_o), ('e', ft_e))) if f)
    page_css = f'@page{name}{{size:{PT(pw)} {PT(ph)};margin:{mg};{mbox}}}\n{parity}{side_css}' + run
    if idx: screen = f'.page.s{idx}{{width:{PT(pw)};min-height:{PT(ph)};padding:{mg}}}\n'
    else: screen = f'.page{{width:{PT(pw)};min-height:{PT(ph)};margin:24px auto;padding:{mg};box-sizing:border-box;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,.15)}}\n'
    return body, page_css, screen, first


def convert(src, dst):
    load(src)
    LAST_HF['head'] = LAST_HF['foot'] = (None, None)
    secs = []
    while True:         # Section0, Section1, … (예전엔 첫 구역만 읽어 둘째 구역부터의 글이 통째로 사라졌다)
        try: raw = c.read('/BodyText/Section%d' % len(secs))
        except KeyError: break
        secs.append(tree(records(dec(raw))))
    if not secs: raise ValueError('본문(BodyText)이 없는 파일')
    parts = [build_section(root, i) for i, root in enumerate(secs)]
    title = html.escape(parts[0][3] or Path(src).stem)
    if parts[0][1]:
        page_css = parts[0][1] + ''.join(p[1] for p in parts[1:]) + ''.join(p[2] for p in parts)
        page_css += '@media print{body{background:#fff}.page{box-shadow:none;margin:0;padding:0;width:auto;min-height:0}}'
    else:                       # 쪽 설정을 못 찾은 문서는 예전 화면용 모양
        page_css = ('.page{max-width:794px;margin:24px auto;background:#fff;padding:56px 64px;box-shadow:0 2px 10px rgba(0,0,0,.15);box-sizing:border-box}\n'
                    '@media print{body{background:#fff}.page{box-shadow:none;margin:0;max-width:none}}\n'
                    '@media (max-width:600px){.page{padding:24px 16px;margin:0}}')
    body = '\n'.join('<div class="page%s"%s>\n%s\n</div>' % (*((f' s{i}', f' style="page:s{i}"') if i else ('', '')), p[0]) for i, p in enumerate(parts))
    page = f'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{margin:0;background:#e9eaec;font-family:"함초롬바탕","HCR Batang","Batang","Noto Serif KR","Malgun Gothic",serif;color:#000}}
{page_css}
p{{margin:0;word-break:keep-all;overflow-wrap:break-word;orphans:1;widows:1}}
@media print{{.pgno::before{{content:counter(page)}} .mo{{position:fixed;left:var(--cx);top:var(--cy)}} .mo.mm{{display:none}} .fo{{position:absolute;left:var(--cx);top:var(--cy)}}}}      /* 쪽 여백 안(mm)의 바탕쪽 개체는 크롬·엣지 인쇄가 여백에 못 그리고 엉뚱한 쪽 아래로 밀어 글과 겹친다 → 숨긴다. PDF 변환(WeasyPrint)은 convert.PDF_CSS 가 다시 보이게 한다 */
@media screen{{.page{{position:relative}} .mo,.fo{{position:absolute;left:var(--px);top:var(--py)}}}}
.tl{{flex:0 1 auto}} .tr{{flex:0 0 auto;text-align:right}} .tf{{flex:1 1 auto;margin:0 .2em;min-width:.5em;height:.8em}}
.hwp-table{{border-collapse:collapse}}
.hwp-table td{{box-sizing:border-box;word-break:keep-all}}
figure{{margin:4px 0;text-align:center}} figure img{{max-width:100%;height:auto}}
.mid{{font-family:'바탕','Batang','Nanum Myeongjo',serif}}
</style></head>
<body>
{body}
</body></html>'''
    page = mid_dot(page)
    Path(dst).write_text(page, encoding='utf-8')
    if SKIPPED: print(f'경고: 읽을 수 없는 그림 {len(SKIPPED)}개를 뺐습니다 (벡터·깨진 그림: {", ".join(sorted(set(SKIPPED)))})', file=sys.stderr)
    return dict(bytes=len(page), images=[s for _, s in IMAGES], tables=page.count('<table'), fonts=sorted({cs['face'] for cs in charshapes if cs['face']}))


if __name__ == '__main__':
    print(convert(sys.argv[1], sys.argv[2]))
