FROM node:22.15.0-alpine AS frontend
WORKDIR /build
RUN npm install -g pnpm@10.10.0
COPY frontend/package.json ./
RUN pnpm install
COPY frontend/ ./
RUN pnpm build
FROM python:3.12.10-slim
WORKDIR /app
COPY backend/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist
RUN useradd --create-home stockroom
USER stockroom
EXPOSE 8000
CMD ["uvicorn","backend.app:app","--host","0.0.0.0","--port","8000"]
