FROM python:3.12-slim

# 읽기 전용 파일시스템에서 돌리므로 바이트코드를 쓰지 않고, HOME은 쓰기 가능한 tmpfs(/tmp)로 둔다
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp

# 화면·변환기가 실제로 쓰는 것만, 시험한 버전으로 고정한다 (requirements.txt에는 아직 안 쓰는 패키지가 섞여 있다)
RUN pip install --no-cache-dir streamlit==1.65.0 lxml==6.1.3 pillow==12.3.0

WORKDIR /app
COPY app.py convert.py hwp2html.py hwpx2html.py html2hwpx.py ./
COPY .streamlit .streamlit

RUN useradd --uid 10001 --no-create-home app && mkdir logs && chown app logs
USER app

EXPOSE 8501
# 컨테이너 안에서는 0.0.0.0이어야 호스트 포트 매핑으로 닿는다. 외부 노출은 compose.yaml의 127.0.0.1 매핑으로 막는다
CMD ["streamlit", "run", "app.py", "--server.headless=true", "--server.address=0.0.0.0", "--server.port=8501"]
