# Base image ships a Chromium build that matches the `playwright` pip
# version pinned in requirements.txt — needed for demo_video_producer's
# screenshot capture. If you bump the pip pin, bump this tag to match.
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

# ffmpeg (video rendering) + DejaVu fonts (caption/title-card text) for
# demo_video_producer. Everything else Playwright needs is already in the
# base image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=5000
EXPOSE 5000

# Shell form so $PORT (set by Railway at runtime) actually expands.
CMD gunicorn server:app --timeout 600 --workers 1 --bind 0.0.0.0:${PORT:-5000}
