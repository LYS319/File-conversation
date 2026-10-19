FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 fontconfig fonts-nanum fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir weasyprint pymupdf lxml pillow
COPY fonts.conf /etc/fonts/conf.d/99-korean-aliases.conf
RUN fc-cache -f
