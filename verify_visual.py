"""시각 검수: 한컴이 만든 정답 PDF 와 우리 변환 PDF 를 쪽별로 Claude(비전)에게 보여 주고, 눈에 띄는 차이를 구조화된 목록으로 받는다.
    python verify_visual.py 코퍼스폴더(manifest.json) 변환PDF폴더 출력폴더 [--model M] [--pages 3] [--only 글자] [--control]
변환PDF폴더 = check_layout.py 가 만든 폴더(NN_이름.pdf, manifest 순서). 출력: 문서별 JSON + report.md.
주의: 문서 이미지가 Anthropic API 로 나간다. 공개 문서(rhwp 코퍼스)에만 쓸 것 — 사내 문서는 조직 승인 후.
--control: 정답 PDF 를 자기 자신과 비교해 거짓 경보(차이가 없는데 있다고 말함)가 얼마나 나오는지 잰다."""
import argparse, base64, json, os, sys, time, urllib.request, uuid
from datetime import datetime, timezone
from pathlib import Path
import anthropic, pymupdf
from dotenv import load_dotenv

CATS = ['missing_content', 'extra_content', 'broken_glyph', 'missing_graphic', 'table_structure', 'layout_shift', 'page_break', 'text_wrapping', 'style_color', 'other']
TOOL = {'name': 'report_issues', 'description': '정답(한컴)과 변환 결과를 비교한 검수 결과를 보고한다.', 'input_schema': {'type': 'object', 'properties': {
    'similarity': {'type': 'integer', 'minimum': 1, 'maximum': 5, 'description': '5=차이를 못 찾겠음, 1=전혀 다른 문서'},
    'summary': {'type': 'string', 'description': '한국어 한두 문장 총평'},
    'issues': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'page': {'type': 'integer'}, 'category': {'type': 'string', 'enum': CATS}, 'severity': {'type': 'string', 'enum': ['high', 'medium', 'low']},
        'description': {'type': 'string', 'description': '한국어. 무엇이(어떤 글·표·그림이) 어떻게 다른지 구체적으로'}, 'location': {'type': 'string', 'description': '쪽 안 대략 위치(위/가운데/아래, 왼/오른쪽)'}},
        'required': ['page', 'category', 'severity', 'description', 'location']}}}, 'required': ['similarity', 'summary', 'issues']}}
SYSTEM = ('당신은 문서 변환 품질 검수자다. HWP 문서를 한컴이 그린 정답 이미지(REF)와, 변환기가 만든 결과 이미지(OUT)를 쪽별로 비교한다. '
          '사용자가 실제로 알아챌 차이만 보고한다: 빠지거나 더 생긴 글·표·그림, 깨진 글자(네모·물음표), 표 구조·테두리·음영 차이, 큰 위치 이동, 쪽 나눔·쪽 수 차이, 줄바꿈이 크게 달라진 곳. '
          '무시: 글꼴 서체·글자 굵기 모양의 미세한 차이(OUT 은 나눔 글꼴을 쓴다), 3pt 안쪽의 위치 차이, 같은 내용의 안티앨리어싱 차이. '
          '차이가 없으면 issues 를 빈 목록으로 두고 similarity 5 로 답한다. 추측하지 말고 이미지에서 보이는 것만 쓴다.')


def png(page, scale):
    return base64.standard_b64encode(page.get_pixmap(matrix=pymupdf.Matrix(scale, scale)).tobytes('png')).decode()


def blocks(ref, out, pages, scale):
    c = [{'type': 'text', 'text': f'REF(한컴 정답) 총 {len(ref)}쪽, OUT(변환 결과) 총 {len(out)}쪽. 아래에 쪽마다 REF 다음 OUT 이미지를 보낸다(앞 {pages}쪽까지).'}]
    for i in range(min(pages, max(len(ref), len(out)))):
        for tag, doc in (('REF', ref), ('OUT', out)):
            if i < len(doc):
                c.append({'type': 'text', 'text': f'[{tag} {i + 1}쪽]'})
                c.append({'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': png(doc[i], scale)}})
            else:
                c.append({'type': 'text', 'text': f'[{tag} {i + 1}쪽] 없음(이 쪽은 {tag} 에 존재하지 않는다)'})
    return c


def judge(client, model, content):
    # 이 모델은 tool_choice 강제(tool/any)를 지원하지 않는다 -> 자동 선택 + 지시문으로 호출을 요구하고, 안 부르면 한 번 더 요청
    kw = dict(model=model, max_tokens=4000, system=SYSTEM + ' 답은 반드시 report_issues 도구 호출로만 한다.', tools=[TOOL], messages=[{'role': 'user', 'content': content}])
    # 스키마를 강제할 수 없으니 필수 항목이 다 있는지 직접 확인하고, 모자라면 한 번 더 요청(최대 3번)
    # issues 는 필수(항목마다 필수 칸 확인). similarity·summary 는 가끔 빠져서 선택으로 두고 빈 값으로 채운다(점수가 빠졌다고 검수를 버리지 않는다)
    need = ['category', 'severity', 'description']        # page·location 도 가끔 빠진다 -> 기본값으로 채운다
    for _ in range(3):
        r = client.messages.create(**kw)
        tu = next((b for b in r.content if b.type == 'tool_use'), None)
        if tu and isinstance(tu.input.get('issues'), list) and all(isinstance(x, dict) and all(k in x for k in need) for x in tu.input['issues']):
            for x in tu.input['issues']: x.setdefault('page', 0); x.setdefault('location', '')
            return {'similarity': None, 'summary': '', **tu.input}, r.usage
    raise RuntimeError('report_issues 결과가 스키마에 맞지 않음: ' + str(tu.input if tu else [b.type for b in r.content])[:200])


def lf_log(doc, model, res, usage, t0, t1, control):
    """Langfuse 에 검수 호출을 남긴다(SDK 없이 공개 수집 API, 로컬 서버). 이미지는 빼고 문서 이름·결과·토큰만. 실패해도 검수는 계속한다."""
    # 이 Langfuse 서버는 v4(events_only)라 옛 /api/public/ingestion 은 점수 이벤트만 받는다(207 + 오류 본문). 그래서 OpenTelemetry(OTLP/JSON) 경로로 보낸다.
    try:
        base = os.environ['LANGFUSE_BASE_URL'].rstrip('/'); key = f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}"
        s = lambda k, v: {'key': k, 'value': {'stringValue': v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}}
        attrs = [s('langfuse.observation.type', 'generation'), s('langfuse.observation.model.name', model), s('langfuse.observation.input', doc), s('langfuse.observation.output', res),
                 s('langfuse.trace.name', 'verify_visual'), s('langfuse.trace.input', doc), s('langfuse.trace.output', res),
                 {'key': 'langfuse.trace.tags', 'value': {'arrayValue': {'values': [{'stringValue': t} for t in ['verify_visual'] + (['control'] if control else [])]}}}]
        if usage: attrs.append(s('langfuse.observation.usage_details', {'input': usage.input_tokens, 'output': usage.output_tokens}))
        span = {'traceId': uuid.uuid4().hex, 'spanId': uuid.uuid4().hex[:16], 'name': 'judge', 'kind': 1, 'startTimeUnixNano': str(int(t0 * 1e9)), 'endTimeUnixNano': str(int(t1 * 1e9)), 'attributes': attrs}
        body = {'resourceSpans': [{'resource': {'attributes': [s('service.name', 'verify_visual')]}, 'scopeSpans': [{'scope': {'name': 'verify_visual'}, 'spans': [span]}]}]}
        req = urllib.request.Request(base + '/api/public/otel/v1/traces', json.dumps(body).encode(), {'Authorization': 'Basic ' + base64.b64encode(key.encode()).decode(),
                                     'Content-Type': 'application/json', 'x-langfuse-ingestion-version': '4'})
        out = urllib.request.urlopen(req, timeout=10).read().decode()
        if 'rejected' in out.lower() and '"rejectedSpans":"0"' not in out.replace(' ', '') and '"rejectedSpans":0' not in out.replace(' ', ''): raise RuntimeError(out[:150])
    except Exception as e:
        print('  (Langfuse 기록 실패:', type(e).__name__, str(e)[:120], ')', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('corpus'); ap.add_argument('cand'); ap.add_argument('out')
    ap.add_argument('--model', default='claude-sonnet-5-5'); ap.add_argument('--pages', type=int, default=3); ap.add_argument('--scale', type=float, default=1.3)
    ap.add_argument('--only', default=''); ap.add_argument('--control', action='store_true')
    a = ap.parse_args()
    load_dotenv(Path(__file__).resolve().parents[0] / '.env')
    client = anthropic.Anthropic(); corpus, cand, outd = Path(a.corpus), Path(a.cand), Path(a.out); outd.mkdir(parents=True, exist_ok=True)
    man = [m for m in json.loads((corpus / 'manifest.json').read_text(encoding='utf-8')) if 'oracle_pdf' in m]
    rows, tin, tout = [], 0, 0
    for i, m in enumerate(man):
        stem = Path(m['path']).stem
        if a.only and a.only not in m['path']: continue
        jf = outd / f'{i:02d}_{stem}.json'; t = time.time()
        if jf.exists():         # 이어하기: 이미 검수한 문서는 다시 부르지 않는다(비용, 그리고 결과가 매번 달라지는 것 방지)
            res = json.loads(jf.read_text(encoding='utf-8')); nref, nout = res['ref_pages'], res['out_pages']
        else:
            ref = pymupdf.open(str(corpus / m['oracle_pdf']))
            out = ref if a.control else pymupdf.open(str(cand / f'{i:02d}_{stem}.pdf')); nref, nout = len(ref), len(out)
            res, u = judge(client, a.model, blocks(ref, out, a.pages, a.scale))
            tin += u.input_tokens; tout += u.output_tokens; lf_log(m['path'], a.model, res, u, t, time.time(), a.control)
            jf.write_text(json.dumps({'doc': m['path'], 'ref_pages': nref, 'out_pages': nout, **res}, ensure_ascii=False, indent=1), encoding='utf-8')
        hi = sum(x['severity'] == 'high' for x in res['issues'])
        rows.append((m['path'], nref, nout, res['similarity'], len(res['issues']), hi, f'{time.time() - t:.0f}s', res['summary']))
        print(rows[-1][:7], flush=True)
    lines = ['문서 | 정답쪽 | 결과쪽 | 유사도(1-5) | 문제 수 | high | 시간 | 총평'] + [' | '.join(str(c) for c in r) for r in rows]
    lines.append(f'\n모델 {a.model} · 입력 토큰 {tin:,} · 출력 토큰 {tout:,}' + (' · (대조군: 정답끼리 비교)' if a.control else ''))
    (outd / 'report.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
