#!/bin/sh
# 시험용 이미지 pdftest:wp 를 만든다: 앱 이미지와 같은 글꼴(나눔·Liberation·Carlito·Caladea)+fonts.conf + weasyprint·pymupdf·pillow.
# 앱 Dockerfile 의 글꼴 목록이나 fonts.conf 를 바꾸면 이것도 다시 만들어야 측정이 앱과 같아진다.
cd "$(dirname "$0")" && cp ../fonts.conf fonts.conf && docker build -t pdftest:wp . && rm fonts.conf
