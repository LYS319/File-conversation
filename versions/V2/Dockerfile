FROM python:3.12-slim

# 읽기 전용 파일시스템에서 돌리므로 바이트코드를 쓰지 않고, HOME은 쓰기 가능한 tmpfs(/tmp)로 둔다
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp XDG_CACHE_HOME=/tmp/.cache

# PDF 엔진(WeasyPrint)이 쓰는 글자 그리기 라이브러리(Pango)와 무료 글꼴(나눔, SIL OFL). 한컴 글꼴은 없으므로 fonts.conf 가 이름을 나눔 글꼴로 대신한다
RUN apt-get update && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 fontconfig fonts-nanum fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY fonts.conf /etc/fonts/conf.d/99-korean-aliases.conf
RUN fc-cache -f

# 화면·변환기가 실제로 쓰는 것만, 시험한 버전으로 고정한다 (requirements.txt에는 아직 안 쓰는 패키지가 섞여 있다)
RUN pip install --no-cache-dir streamlit==1.65.0 lxml==6.1.3 pillow==12.3.0 weasyprint==70.0

# hwp-cli (MIT 또는 Apache-2.0): HWP -> HWPX 직접 변환. 공식 릴리스를 받아, 릴리스에 공개된 체크섬과 같을 때만 설치한다(다르면 빌드 실패). 라이선스 문서도 함께 둔다
RUN python - <<'EOF'
import hashlib, io, os, tarfile, urllib.request
URL = 'https://github.com/STAIxBWLB/hwp-cli/releases/download/v1.3.1/hwp-v1.3.1-x86_64-unknown-linux-gnu.tar.gz'
SHA = '21bd8ab3b6834c48fcebca390e3d3f79dcedd6a4388e4eeaf802501f84fcf433'
data = urllib.request.urlopen(URL, timeout=120).read()
assert hashlib.sha256(data).hexdigest() == SHA, 'hwp-cli 체크섬 불일치'
tf = tarfile.open(fileobj=io.BytesIO(data)); os.makedirs('/usr/share/doc/hwp-cli', exist_ok=True)
for name, dest, mode in (('hwp', '/usr/local/bin/hwp', 0o755), ('LICENSE-MIT', '/usr/share/doc/hwp-cli/LICENSE-MIT', 0o644), ('LICENSE-APACHE', '/usr/share/doc/hwp-cli/LICENSE-APACHE', 0o644), ('NOTICE', '/usr/share/doc/hwp-cli/NOTICE', 0o644)):
    open(dest, 'wb').write(tf.extractfile(name).read()); os.chmod(dest, mode)
EOF

WORKDIR /app
COPY app.py convert.py approval.py hwp2html.py hwpx2html.py html2hwpx.py ./
COPY .streamlit .streamlit

RUN useradd --uid 10001 --no-create-home app && mkdir logs && chown app logs
USER app

EXPOSE 8501
# 컨테이너 안에서는 0.0.0.0이어야 호스트 포트 매핑으로 닿는다. 외부 노출은 compose.yaml의 127.0.0.1 매핑으로 막는다
CMD ["streamlit", "run", "app.py", "--server.headless=true", "--server.address=0.0.0.0", "--server.port=8501"]
